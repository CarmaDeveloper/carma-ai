"""Main FastAPI application."""

import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1.api import api_router_v1
from app.core.auth import AuthenticationMiddleware, api_key_header
from app.core.config import settings
from app.core.langfuse import init_langfuse, shutdown_langfuse
from app.core.logging import setup_logger
from app.db.database import Base, async_session_factory, engine
from app.repositories.session_repo import SessionRepository


def cleanup_retry_delay(failures: int) -> int:
    """Seconds until the next try after the given number of failed runs in a row.

    The first retry is after CHATBOT_CLEANUP_RETRY_SECONDS. The delay doubles on
    each failure and is never longer than CHATBOT_CLEANUP_INTERVAL_SECONDS.
    """
    interval = settings.CHATBOT_CLEANUP_INTERVAL_SECONDS
    delay = settings.CHATBOT_CLEANUP_RETRY_SECONDS * 2 ** min(failures - 1, 16)
    return min(delay, interval)


async def run_session_cleanup() -> None:
    """Delete old chat sessions now and then every CHATBOT_CLEANUP_INTERVAL_SECONDS.

    A failed run is tried again soon (see cleanup_retry_delay). A paused Aurora
    Serverless database wakes up on the first connection, but that connection
    can fail before the database is awake. The retry then finds it awake.
    """
    logger = setup_logger(__name__)
    failures = 0
    while True:
        try:
            async with async_session_factory() as session:
                await SessionRepository(session).delete_old_sessions(
                    settings.CHATBOT_SESSION_RETENTION_DAYS
                )
            failures = 0
            delay = settings.CHATBOT_CLEANUP_INTERVAL_SECONDS
        except Exception as e:
            failures += 1
            delay = cleanup_retry_delay(failures)
            # One failure is expected when the database is paused, so it is a warning.
            log = logger.warning if failures == 1 else logger.error
            log(
                f"Chat session cleanup failed: {type(e).__name__} "
                f"(failure {failures} in a row, next try in {delay} s)"
            )
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    logger = setup_logger(__name__)
    logger.info(f"Starting CARMA AI Application, version={app.version}")

    # Initialize Langfuse observability
    init_langfuse()

    # Initialize database tables only if configured to do so (e.g., in development).
    # In production, use Alembic migrations instead.
    if settings.CREATE_TABLES:
        try:
            async with engine.begin() as conn:
                # Create all tables defined in Base.metadata
                await conn.run_sync(Base.metadata.create_all)
                logger.info(
                    "Database tables initialized successfully (CREATE_TABLES is True)"
                )
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}", exc_info=True)
            raise
    else:
        logger.info(
            "Skipping auto table creation (CREATE_TABLES is False, using Alembic migrations)"
        )

    cleanup_task = asyncio.create_task(run_session_cleanup())

    yield

    # Shutdown
    logger.info("Shutting down CARMA AI Application")
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task
    shutdown_langfuse()


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    # The API docs are not served in production.
    show_docs = settings.ENVIRONMENT != "production"
    app = FastAPI(
        title=settings.APP_NAME,
        description="CARMA AI",
        version="0.1.0",
        docs_url="/docs" if show_docs else None,
        redoc_url="/redoc" if show_docs and settings.DEBUG else None,
        openapi_url="/openapi.json" if show_docs else None,
        servers=[
            {
                "url": f"http://localhost:{settings.DOCS_PORT}",
                "description": "Local Enviroment",
            }
        ],
        lifespan=lifespan,
    )

    app.add_middleware(AuthenticationMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(health.router)
    app.include_router(api_router_v1, dependencies=[Depends(api_key_header)])

    return app


app = create_application()
