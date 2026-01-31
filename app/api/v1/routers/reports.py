"""Report generation endpoints."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.exceptions import ComprehendError, ModelError, VectorStoreError
from app.core.logging import setup_logger
from app.dependencies import get_report_service
from app.schemas.report import (
    ReportGenerationRequest,
    ReportGenerationResponse,
    InsightGenerationRequest,
)
from app.services.report import ReportGenerationService

logger = setup_logger(__name__)

router = APIRouter(prefix="/reports")


@router.post(
    "/generate",
    response_model=ReportGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a report using RAG methodology",
)
async def generate_report(
    request: ReportGenerationRequest,
    report_service: ReportGenerationService = Depends(get_report_service),
) -> ReportGenerationResponse:
    """
    Generate a report using RAG methodology.

    This endpoint:
    1. Processes answers through AWS Comprehend for PII redaction
    2. Retrieves relevant context from vector store (if knowledge_id provided)
    3. Uses LLM to generate comprehensive report
    4. Returns generated report with references

    Args:
        request: Report generation request containing QAs, prompt, and optional knowledge_id

    Returns:
        Generated report with message, references, and knowledge_id

    Raises:
        HTTPException:
            - 500: If report generation fails due to model, vector store, or comprehend errors
    """
    try:
        logger.info(
            f"API: Generating report - knowledge_id: {request.knowledge_id}, "
            f"qa_count: {len(request.qas)}, prompt_length: {len(request.prompt)}"
        )

        response = await report_service.generate_report(request)

        logger.info(
            f"API: Report generated successfully - knowledge_id: {request.knowledge_id}, "
            f"message_length: {len(response.message)}, references: {len(response.references)}"
        )

        return response

    except ComprehendError as e:
        logger.error(f"Comprehend service error during report generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PII redaction failed during report generation",
        )
    except VectorStoreError as e:
        logger.error(f"Vector store error during report generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Context retrieval failed during report generation",
        )
    except ModelError as e:
        logger.error(f"Model error during report generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM generation failed during report generation",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during report generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during report generation",
        )


@router.post(
    "/insights/stream",
    summary="Generate insights from patient report data (Streaming)",
    status_code=status.HTTP_200_OK,
)
async def generate_insights_stream(
    request: InsightGenerationRequest,
    report_service: ReportGenerationService = Depends(get_report_service),
) -> StreamingResponse:
    """
    Generate insights from patient report data and stream the response.

    This endpoint streams the following events:
    - `insight.init`: Initialization of the generation process.
    - `insight.metadata`: Metadata including references (filenames), document_ids, and knowledge_id.
    - `insight.references`: List of references with user-defined title and S3 download URL.
    - `insight.content`: Chunks of the generated content.
    - `insight.complete`: Completion of the generation.
    - `insight.error`: Error occurred.

    Args:
        request: JSON body containing the list of report items.

    Returns:
        StreamingResponse: SSE stream.
    """
    try:
        async def event_generator():
            try:
                async for event_type, data in report_service.stream_insight_generation(
                    request
                ):
                    yield report_service.format_sse_event(event_type, data)
            except asyncio.CancelledError:
                logger.info("Client disconnected from insight stream.")
                raise
            except Exception as e:
                logger.error(f"Error in insight event generator: {e}", exc_info=True)
                yield report_service.format_sse_event(
                    "insight.error",
                    {"error": "An unexpected error occurred during insight generation"},
                )

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Failed to initialize insight stream: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize insight generation",
        )
