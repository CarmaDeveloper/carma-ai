"""Authentication middleware and utilities."""

import secrets

from fastapi import HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)

# Security schemes for OpenAPI documentation
# This allows Swagger UI to show the "Authorize" button and send the headers
api_key_header = APIKeyHeader(name="Ai-Token", auto_error=False)
user_id_header = APIKeyHeader(name="User-ID", auto_error=False)


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


async def get_user_id(
    user_id: str = Header(..., alias="User-ID", description="User identifier for tracking and observability")
) -> str:
    """
    FastAPI dependency to extract and validate user_id from request headers.

    This dependency requires the 'User-ID' header to be present in the request.
    It follows FastAPI best practices for extracting headers as dependencies.

    Args:
        user_id: User identifier from 'User-ID' header

    Returns:
        str: The user ID

    Raises:
        HTTPException: If User-ID header is missing or invalid
    """
    if not user_id or not user_id.strip():
        logger.warning("Invalid or empty User-ID header provided")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid User-ID header",
        )

    logger.debug(f"Extracted user_id: {user_id}")
    return user_id.strip()


async def get_optional_user_id(
    user_id: str = Header(None, alias="User-ID", description="Optional user identifier for tracking and observability")
) -> str | None:
    """
    FastAPI dependency to optionally extract user_id from request headers.

    This dependency allows the 'User-ID' header to be optional.
    If provided, it validates and returns the user_id. If not provided, returns None.

    Args:
        user_id: Optional user identifier from 'User-ID' header

    Returns:
        str | None: The user ID if provided and valid, None otherwise
    """
    if user_id and user_id.strip():
        logger.debug(f"Extracted optional user_id: {user_id}")
        return user_id.strip()
    
    logger.debug("No User-ID header provided")
    return None
