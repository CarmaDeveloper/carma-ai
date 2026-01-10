"""API router for template generation."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.logging import setup_logger
from app.schemas.template import TemplateGenerationRequest
from app.services.template import TemplateService
from app.dependencies.get_template_service import get_template_service

logger = setup_logger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post(
    "/stream",
    summary="Stream template generation via SSE",
    status_code=status.HTTP_200_OK,
)
async def stream_template(
    request: TemplateGenerationRequest,
    template_service: TemplateService = Depends(get_template_service),
) -> StreamingResponse:
    """
    Generate and stream a template (title and content) based on a prompt using Server-Sent Events (SSE).

    This endpoint streams the following events:
    - `template.init`: Metadata about the generation process.
    - `template.title`: Chunks of the generated title.
    - `template.content`: Chunks of the generated content (markdown).
    - `template.complete`: Signal that generation is finished.
    - `template.error`: If an error occurs during generation.

    Args:
        request: JSON body containing the `prompt`.

    Returns:
        StreamingResponse: SSE stream with media type `text/event-stream`.
    """
    try:
        async def event_generator():
            try:
                async for event_type, data in template_service.stream_template_generation(
                    request.prompt
                ):
                    yield template_service.format_sse_event(event_type, data)
            except asyncio.CancelledError:
                logger.info("Client disconnected from template stream.")
                raise
            except Exception as e:
                logger.error(f"Error in template event generator: {e}", exc_info=True)
                yield template_service.format_sse_event(
                    "template.error", 
                    {"error": str(e), "message": "Unexpected error during streaming"}
                )

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Failed to initialize template stream: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize template generation",
        )
