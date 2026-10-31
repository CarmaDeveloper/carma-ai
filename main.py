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


async def run_session_cleanup() -> None:
    """Delete old chat sessions now and then every CHATBOT_CLEANUP_INTERVAL_SECONDS."""
    logger = setup_logger(__name__)
    while True:
        try:
            async with async_session_factory() as session:
                await SessionRepository(session).delete_old_sessions(
                    settings.CHATBOT_SESSION_RETENTION_DAYS
                )
        except Exception as e:
            logger.error(f"Chat session cleanup failed: {type(e).__name__}")
        await asyncio.sleep(settings.CHATBOT_CLEANUP_INTERVAL_SECONDS)


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
