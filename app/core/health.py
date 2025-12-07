"""Health check module for application monitoring."""

from typing import Optional
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import setup_logger
from app.db.database import engine

logger = setup_logger(__name__)


async def check_database_connection() -> bool:
    """Check if the database connection is healthy."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
    return True


def get_health_status(db_status: Optional[bool]):
    """
    Get health status response.

    Args:
        db_status: Database status (True/False) or None to skip database check
    """
    if db_status is None:
        # Basic health check - application is running
        return {
            "message": "Service is healthy",
            "data": {
                "status": "healthy",
                "app": settings.APP_NAME,
                "database": "not_checked",
            },
        }
    else:
        # Deep health check - includes database status
        status = "healthy" if db_status else "unhealthy"
        return {
            "message": f"Service is {status}",
            "data": {"status": status, "app": settings.APP_NAME, "database": db_status},
        }
