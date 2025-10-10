"""SSE Chatbot API endpoints with session management."""

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse

from app.core.logging import setup_logger
from app.models.chatbot import ChatbotRequest
from app.services.chatbot import chatbot_service

logger = setup_logger(__name__)

router = APIRouter(tags=["chatbot"], prefix="/v1/chatbot")


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream chatbot conversation via Server-Sent Events with session management",
)
async def stream_chatbot(request: ChatbotRequest) -> StreamingResponse:
    """
    Stream chatbot responses using Server-Sent Events (SSE) with conversation memory.

    This endpoint:
    1. Accepts a user message and optional session_id
    2. If no session_id is provided, generates a new one (sent as first SSE event)
    3. Maintains conversation history per session using in-memory storage
    4. Streams model output as SSE events
    5. Emits a final `done` event to signal completion

    **SSE Event Types (all data is JSON):**
    - `chatbot.session`: `{"session_id": "...", "is_new": true/false}`
    - `chatbot.chunk`: `{"content": "chunk of text"}`
    - `chatbot.complete`: `{"status": "complete"}`
    - `chatbot.error`: `{"error": "error message", "message": "description"}`

    Args:
        request: ChatbotRequest containing the user message and optional session_id

    Returns:
        StreamingResponse: SSE stream with media type `text/event-stream`

    Raises:
        HTTPException: On server errors before streaming begins (500).
        Errors during streaming are sent within the SSE stream as error events.
    """
    try:

        async def event_generator():
            """Generate SSE events from the chatbot service."""
            try:
                async for event_type, data in chatbot_service.stream_chat(
                    message=request.message, session_id=request.session_id
                ):
                    # Format as SSE event with JSON data
                    sse_message = chatbot_service.format_sse_event(event_type, data)
                    yield sse_message
            except asyncio.CancelledError:
                logger.info(
                    "Client disconnected from chatbot stream. Closing generator."
                )
                raise
            except Exception as e:
                logger.error(f"Error in event generator: {e}", exc_info=True)
                error_event = chatbot_service.format_sse_event(
                    "chatbot.error",
                    {"error": str(e), "message": "Streaming error occurred"},
                )
                yield error_event

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Chatbot streaming failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize chat stream",
        )


@router.get(
    "/sessions/stats",
    status_code=status.HTTP_200_OK,
    summary="Get session statistics",
)
async def get_session_stats() -> JSONResponse:
    """
    Get statistics about active chatbot sessions.

    Returns information about:
    - Total number of sessions in memory
    - Number of active (non-expired) sessions
    - Maximum session limit
    - Session TTL configuration

    This endpoint is useful for monitoring memory usage and session health.

    Returns:
        JSONResponse with session statistics
    """
    try:
        stats = await chatbot_service.get_session_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error(f"Failed to get session stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session statistics",
        )
