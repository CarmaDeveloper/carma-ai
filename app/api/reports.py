"""Report generation endpoints."""

from fastapi import APIRouter, status

from app.core.logging import setup_logger
from app.models.report import ReportGenerationRequest, ReportGenerationResponse
from app.services.report import report_service

logger = setup_logger(__name__)

router = APIRouter(tags=["reports"], prefix="/v1/reports")


@router.post(
    "/generate",
    response_model=ReportGenerationResponse,
    status_code=status.HTTP_200_OK,
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
    """
    return await report_service.generate_report(request)
