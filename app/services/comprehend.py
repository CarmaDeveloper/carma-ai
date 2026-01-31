"""AWS Comprehend service for PII detection and redaction."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.exceptions import ComprehendError
from app.core.logging import setup_logger

logger = setup_logger(__name__)

# Constants
LANGUAGE_CODE = "en"
REPLACE_VIA = "[REDACTED]"


class ComprehendService:
    """AWS Comprehend service for PII detection and redaction."""

    def __init__(self) -> None:
        """Initialize Comprehend client."""
        self.client = boto3.client("comprehend", region_name=settings.COMPREHEND_REGION)
        self.threshold = settings.COMPREHEND_THRESHOLD
        self.entity_types = settings.COMPREHEND_TYPES
        # Thread pool for running blocking boto3 calls
        self._executor = ThreadPoolExecutor(
            max_workers=settings.COMPREHEND_MAX_CONCURRENT_REQUESTS
        )

    def _detect_pii_sync(self, text: str) -> dict:
        """Synchronous call to AWS Comprehend detect_pii_entities."""
        return self.client.detect_pii_entities(Text=text, LanguageCode=LANGUAGE_CODE)

    async def redact_pii(self, texts: List[str]) -> List[str]:
        """
        Use AWS Comprehend to filter personal information from texts.

        Processes texts concurrently using a thread pool executor to avoid
        blocking the event loop with boto3's synchronous I/O operations.

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
            # Process all texts concurrently
            tasks = [self._process_text(text) for text in texts]
            result = await asyncio.gather(*tasks)

            logger.info(f"Completed PII redaction: processed_count={len(result)}")
            return result

        except (BotoCoreError, ClientError) as e:
            logger.error(f"AWS Comprehend error: {str(e)}")
            raise ComprehendError(f"Comprehend service error: {str(e)}")

    async def _process_text(self, text: str) -> str:
        """Process a single text for PII detection and redaction."""
        try:
            # Skip empty texts
            if not text or not text.strip():
                return text

            # Run blocking boto3 call in thread pool to avoid blocking event loop
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                self._executor, self._detect_pii_sync, text
            )

            entities = response.get("Entities", [])
            redacted_text = self._redact_entities(text, entities)
            return redacted_text

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
