"""AWS Comprehend service for PII detection and redaction."""

from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.exceptions import ComprehendError
from app.core.logging import setup_logger

logger = setup_logger(__name__)

# Constants
LANGUAGE_CODE = "en"
BATCH_SIZE = 25
REPLACE_VIA = "[REDACTED]"

VALID_ENTITY_TYPES = [
    "COMMERCIAL_ITEM",
    "DATE",
    "EVENT",
    "LOCATION",
    "ORGANIZATION",
    "OTHER",
    "PERSON",
    "QUANTITY",
    "TITLE",
]


class ComprehendService:
    """AWS Comprehend service for PII detection and redaction."""

    def __init__(self) -> None:
        """Initialize Comprehend client."""
        self.client = boto3.client("comprehend", region_name=settings.COMPREHEND_REGION)
        self.threshold = settings.COMPREHEND_THRESHOLD
        self.entity_types = settings.COMPREHEND_TYPES

    async def redact_pii(self, texts: List[str]) -> List[str]:
        """
        Use AWS Comprehend to filter personal information from texts.

        Args:
            texts: List of text strings to process

        Returns:
            List of texts with PII redacted

        Raises:
            ComprehendError: If comprehend processing fails
        """
        if not texts:
            return []

        logger.info(
            f"Starting PII redaction: text_count={len(texts)}, "
            f"threshold={self.threshold}, entity_types={self.entity_types}"
        )

        try:
            result: List[str] = []

            # Process texts in batches
            for i in range(0, len(texts), BATCH_SIZE):
                batch_texts = texts[i : i + BATCH_SIZE]
                redacted_batch = await self._process_batch(batch_texts, i)
                result.extend(redacted_batch)

            logger.info(f"Completed PII redaction: processed_count={len(result)}")
            return result

        except (BotoCoreError, ClientError) as e:
            logger.error(f"AWS Comprehend error: {str(e)}")
            raise ComprehendError(f"Comprehend service error: {str(e)}")

    async def _process_batch(self, batch_texts: List[str], offset: int) -> List[str]:
        """Process a batch of texts for PII detection."""
        try:
            response = self.client.batch_detect_entities(
                TextList=batch_texts, LanguageCode=LANGUAGE_CODE
            )

            if response.get("ErrorList"):
                error_msg = response["ErrorList"][0].get(
                    "ErrorMessage", "Unknown error"
                )
                raise ComprehendError(f"Batch processing error: {error_msg}")

            result = []
            for index, result_item in enumerate(response.get("ResultList", [])):
                original_text = batch_texts[index]
                redacted_text = self._redact_entities(
                    original_text, result_item.get("Entities", [])
                )
                result.append(redacted_text)

            return result

        except KeyError as e:
            raise ComprehendError(f"Unexpected response format: missing {e}")

    def _redact_entities(self, text: str, entities: List[dict]) -> str:
        """Redact identified entities from text."""
        # Sort entities by begin offset in descending order
        # This ensures we don't mess up the offsets when replacing
        sorted_entities = sorted(
            entities, key=lambda x: x.get("BeginOffset", 0), reverse=True
        )

        redacted_text = text
        redacted_count = 0

        for entity in sorted_entities:
            score = entity.get("Score", 0)
            entity_type = entity.get("Type", "")
            begin_offset = entity.get("BeginOffset", 0)
            end_offset = entity.get("EndOffset", 0)

            # Check if entity meets criteria for redaction
            if (
                score >= self.threshold
                and entity_type in self.entity_types
                and begin_offset < end_offset
                and end_offset <= len(redacted_text)
            ):
                # Replace the entity text with redaction marker
                redacted_text = (
                    redacted_text[:begin_offset]
                    + REPLACE_VIA
                    + redacted_text[end_offset:]
                )
                redacted_count += 1

        if redacted_count > 0:
            logger.debug(
                f"Redacted entities from text: original_length={len(text)}, "
                f"redacted_length={len(redacted_text)}, redacted_count={redacted_count}"
            )
            logger.debug(f"Redacted text: {redacted_text}")

        return redacted_text


# Singleton instance
comprehend_service = ComprehendService()
