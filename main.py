"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1.api import api_router_v1
from app.core.auth import AuthenticationMiddleware, api_key_header
from app.core.config import settings
from app.core.logging import setup_logger
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    logger = setup_logger(__name__)
    logger.info(f"Starting CARMA AI Application, version={app.version}")

    # Initialize database tables (create if they don't exist)
    try:
        async with engine.begin() as conn:
            # Create all tables defined in Base.metadata
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down CARMA AI Application")


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="CARMA AI",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc" if settings.DEBUG else None,
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
