"""Comprehend API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import ComprehendError
from app.core.logging import setup_logger
from app.schemas.comprehend import ComprehendRequest, ComprehendResponse
from app.services.comprehend import comprehend_service

logger = setup_logger(__name__)

router = APIRouter(prefix="/comprehend")


@router.post(
    "/redact-pii",
    response_model=ComprehendResponse,
    status_code=status.HTTP_200_OK,
)
async def redact_pii(request: ComprehendRequest) -> ComprehendResponse:
    """
    Redact PII (Personally Identifiable Information) from text using AWS Comprehend.

    This endpoint:
    1. Takes a list of text strings as input
    2. Uses AWS Comprehend to detect entities (names, emails, phone numbers, etc.)
    3. Redacts entities that meet the configured threshold and entity type criteria
    4. Returns the redacted texts

    Args:
        request: List of texts to process for PII redaction

    Returns:
        Redacted texts with PII information replaced with [REDACTED]

    Raises:
        HTTPException: If comprehend processing fails
    """
    try:
        logger.info(f"Processing PII redaction request: {len(request.texts)} texts")

        redacted_texts = await comprehend_service.redact_pii(request.texts)

        logger.info(
            f"Successfully processed PII redaction: {len(redacted_texts)} texts"
        )

        return ComprehendResponse(
            redacted_texts=redacted_texts, processed_count=len(redacted_texts)
        )

    except ComprehendError as e:
        logger.error(f"Comprehend service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comprehend service error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error in comprehend API: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request",
        )
