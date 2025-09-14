"""Health check API endpoints."""

from fastapi import APIRouter, Query

from app.core.health import check_database_connection, get_health_status
from app.core.logging import setup_logger
from app.db.record_manager import record_manager_service

logger = setup_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(
    deep: bool = Query(
        default=False,
        description="Include database connectivity check (will wake Aurora Serverless if paused)",
    )
):
    """
    Health check endpoint with optional deep checking.

    By default, this endpoint only checks if the application is running and does NOT
    check database connectivity to avoid interfering with Aurora Serverless auto-pause.

    Use ?deep=true for comprehensive health checking including database connectivity.
    Note: Deep checking will wake up Aurora Serverless if it's paused.
    """
    if not deep:
        # Basic health check - no database connection test
        return get_health_status(db_status=None)

    # Deep health check - includes database connectivity
    try:
        pool = await record_manager_service.get_pool()
        db_status = await check_database_connection(pool)
    except Exception as e:
        logger.error(f"Deep health check failed to get database pool: {e}")
        db_status = False

    return get_health_status(db_status)
