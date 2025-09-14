"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import reports, health, ingestion, comprehend
from app.core.config import settings
from app.core.logging import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    logger = setup_logger(__name__)
    logger.info(f"Starting CARMA AI Application, version={app.version}")

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
            {"url": "http://localhost:8000", "description": "Local Enviroment"},
            {
                "url": "https://aicarma.bytequest.solutions",
                "description": "Production Environment",
            },
        ],
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(reports.router)
    app.include_router(health.router)
    app.include_router(ingestion.router)
    app.include_router(comprehend.router)

    return app


app = create_application()
