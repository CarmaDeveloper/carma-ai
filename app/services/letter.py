"""Service for generating medical letters via LLM streaming."""

import json
from typing import AsyncGenerator, List, Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import setup_logger
from app.services.llm import LLMService
from app.prompts.letter import LETTER_SYSTEM_PROMPT
from app.schemas.letter import ReportItem

logger = setup_logger(__name__)


class LetterService:
    """Service to handle letter generation with SSE streaming."""

    def __init__(self, llm_service: LLMService):
        """
        Initialize the letter service.

        Args:
            llm_service: Service for LLM interactions
        """
        self.llm_service = llm_service

    async def stream_letter_generation(
        self, report_data: List[ReportItem], instructions: str
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Generate medical letter content from report data and instructions, and stream as events.

        Args:
            report_data: List of patient report data objects
            instructions: User instructions for the letter

        Yields:
            Tuples of (event_type, data_dict)
        """
        logger.info(f"Starting letter generation with instructions: {instructions[:50]}...")

        yield ("letter.init", {"status": "started"})

        try:
            # Serialize report data to JSON for the prompt
            # Using model_dump_json() on each item or converting the list to dicts first
            serialized_report = json.dumps(
                [item.model_dump(mode='json') for item in report_data], 
                indent=2
            )

            prompt_content = (
                f"User Instructions:\n{instructions}\n\n"
                f"Patient Report Data:\n{serialized_report}"
            )

            messages = [
                SystemMessage(content=LETTER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content)
            ]

            logger.debug("Generating letter content...")
            
            async for chunk, _ in self.llm_service.generate_stream(messages):
                if chunk:
                    yield ("letter.content", {"content": chunk})

        except Exception as e:
            logger.error(f"Error generating letter: {e}", exc_info=True)
            yield ("letter.error", {"error": "Failed to generate letter"})
            return

        yield ("letter.complete", {"status": "complete"})
        logger.info("Letter generation completed.")

    def format_sse_event(self, event_type: str, data: dict) -> str:
        """
        Format data as Server-Sent Event with JSON payload.

        Args:
            event_type: Type of the event
            data: Dictionary data to send as JSON

        Returns:
            Formatted SSE string with JSON data
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"

