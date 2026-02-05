"""API router for medical letter generation."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.auth import get_optional_user_id
from app.core.logging import setup_logger
from app.schemas.letter import LetterGenerationRequest
from app.services.letter import LetterService
from app.dependencies.get_letter_service import get_letter_service

logger = setup_logger(__name__)

router = APIRouter(prefix="/letters", tags=["letters"])


@router.post(
    "/stream",
    summary="Stream medical letter generation via SSE",
    status_code=status.HTTP_200_OK,
)
async def stream_letter(
    request: LetterGenerationRequest,
    user_id: str | None = Depends(get_optional_user_id),
    letter_service: LetterService = Depends(get_letter_service),
) -> StreamingResponse:
    """
    Generate and stream a medical letter based on patient report and instructions using Server-Sent Events (SSE).

    This endpoint streams the following events:
    - `letter.init`: Metadata about the generation process.
    - `letter.content`: Chunks of the generated content (markdown).
    - `letter.complete`: Signal that generation is finished.
    - `letter.error`: If an error occurs during generation.

    Args:
        request: JSON body with questionnaireTitle, patientInformation, completedAt,
            report (array of category items), and instructions.

    Returns:
        StreamingResponse: SSE stream with media type `text/event-stream`.
    """
    try:
        async def event_generator():
            try:
                async for event_type, data in letter_service.stream_letter_generation(
                    request, user_id
                ):
                    yield letter_service.format_sse_event(event_type, data)
            except asyncio.CancelledError:
                logger.info("Client disconnected from letter stream.")
                raise
            except Exception as e:
                logger.error(f"Error in letter event generator: {e}", exc_info=True)
                yield letter_service.format_sse_event(
                    "letter.error", 
                    {"error": "An unexpected error occurred during letter generation"}
                )

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Failed to initialize letter stream: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize letter generation",
        )

