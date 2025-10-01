"""Authentication middleware and utilities."""

import secrets

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to check for valid authentication token."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Endpoints that don't require authentication
        self.excluded_paths = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        """Process the request and check authentication."""

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            logger.debug(
                f"Skipping authentication for excluded path: {request.url.path}"
            )
            return await call_next(request)

        # Check for Ai-Token header
        auth_token = request.headers.get("Ai-Token")

        if not auth_token:
            logger.warning(f"Missing Ai-Token header for path: {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing Ai-Token header"},
            )

        if not secrets.compare_digest(auth_token, settings.AUTH_TOKEN):
            logger.warning(f"Invalid Ai-Token for path: {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication token"},
            )

        logger.debug(f"Authentication successful for path: {request.url.path}")
        return await call_next(request)
