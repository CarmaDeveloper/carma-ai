"""SSE Chat API endpoints."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.logging import setup_logger
from app.models.chat import ChatRequest
from app.services.chat import chat_service

logger = setup_logger(__name__)

router = APIRouter(tags=["chat"], prefix="/v1/chat")


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream chat completion via Server-Sent Events",
)
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """
    Stream chat completion using Server-Sent Events (SSE).

    This endpoint:
    1. Accepts a user message
    2. Streams model output as SSE where each chunk is sent as a line prefixed with `data: `
    3. Emits a final `data: [DONE]` event to signal completion

    Args:
        request: ChatRequest containing the user message and the stream flag

    Returns:
        StreamingResponse: SSE stream with media type `text/event-stream`

    Raises:
        HTTPException: If streaming is disabled in the request (400) or on server errors before streaming begins (500). Errors during streaming are sent within the SSE stream.
    """
    try:
        generator = chat_service.stream_chat(message=request.message)
        return StreamingResponse(generator, media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Chat streaming failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream chat response",
        )
