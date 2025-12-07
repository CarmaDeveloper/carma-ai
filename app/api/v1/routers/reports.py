"""Report generation endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import ComprehendError, ModelError, VectorStoreError
from app.core.logging import setup_logger
from app.schemas.report import ReportGenerationRequest, ReportGenerationResponse
from app.services.report import report_service

logger = setup_logger(__name__)

router = APIRouter(prefix="/reports")


@router.post(
    "/generate",
    response_model=ReportGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a report using RAG methodology",
)
async def generate_report(request: ReportGenerationRequest) -> ReportGenerationResponse:
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
