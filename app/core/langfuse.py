"""Langfuse observability integration for LangChain."""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, AsyncGenerator, Dict, List, Optional

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


@lru_cache(maxsize=1)
def get_langfuse_client() -> Optional[Langfuse]:
    """
    Get or create a singleton Langfuse client.

    Returns:
        Langfuse client instance or None if disabled/unavailable.
    """
    if not settings.LANGFUSE_ENABLED:
        return None

    try:
        return Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_BASE_URL,
        )
    except Exception as e:
        logger.error(f"Failed to create Langfuse client: {e}", exc_info=True)
        return None


def init_langfuse() -> bool:
    """
    Initialize and verify Langfuse connection at startup.

    Returns:
        True if Langfuse is enabled and initialized successfully.
    """
    if not settings.LANGFUSE_ENABLED:
        logger.info("Langfuse tracing is DISABLED (LANGFUSE_ENABLED=False)")
        return False

    try:
        client = get_langfuse_client()
        if not client:
            logger.error("Langfuse tracing FAILED: Could not create client")
            return False

        # Verify connection by checking auth
        client.auth_check()

        logger.info(f"Langfuse base URL: {settings.LANGFUSE_BASE_URL}")
        logger.info("Langfuse tracing is ENABLED")
        return True

    except Exception as e:
        logger.error(f"Langfuse tracing FAILED: {e}", exc_info=True)
        return False


def shutdown_langfuse() -> None:
    """Flush and shutdown Langfuse client gracefully."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
            logger.info("Langfuse client flushed successfully")
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse client: {e}")


@asynccontextmanager
async def langfuse_context(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Optional[CallbackHandler], None]:
    """
    Context manager for Langfuse tracing with LangChain.

    Uses propagate_attributes to set user_id, session_id, and other attributes
    that will be attached to all LLM calls made within the context.

    Usage:
        async with langfuse_context(
            user_id="user123",
            session_id="session456",
            trace_name="chatbot.response",
            tags=["chatbot", "rag"],
            metadata={"knowledge_id": "kb-123"}
        ) as handler:
            callbacks = [handler] if handler else None
            await llm_service.generate(messages, callbacks=callbacks)

    Args:
        user_id: User identifier for attribution.
        session_id: Session identifier for grouping related traces.
        trace_name: Name for the trace (e.g., "chatbot.response").
        tags: List of tags for filtering traces.
        metadata: Additional metadata to attach to the trace.

    Yields:
        CallbackHandler instance or None if disabled.
    """
    if not settings.LANGFUSE_ENABLED:
        yield None
        return

    try:
        with propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name,
            tags=tags,
            metadata=metadata,
        ):
            # Create handler inside the propagation context
            handler = CallbackHandler()

            logger.debug(
                f"Langfuse handler created: trace_name={trace_name}, "
                f"user_id={user_id}, session_id={session_id}, tags={tags}"
            )

            yield handler

    except Exception as e:
        logger.warning(f"Failed to create Langfuse context: {e}")
        yield None
