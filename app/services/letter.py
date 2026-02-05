"""Service for generating medical letters via LLM streaming."""

import json
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.langfuse import langfuse_context
from app.core.logging import setup_logger
from app.prompts.letter import LETTER_SYSTEM_PROMPT
from app.schemas.letter import LetterGenerationRequest
from app.services.llm import LLMService

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
        self, request: LetterGenerationRequest, user_id: Optional[str] = None
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Generate medical letter content from the full request and stream as events.

        Uses questionnaireTitle, patientInformation, completedAt at top level (once),
        plus report and instructions per spec.

        Args:
            request: Full letter generation request body
            user_id: Optional user identifier for tracking and observability

        Yields:
            Tuples of (event_type, data_dict)
        """
        instructions = request.instructions
        logger.info(f"Starting letter generation with instructions: {instructions[:50]}...")

        yield ("letter.init", {"status": "started"})

        try:
            # Build header context (once per request)
            header_parts: List[str] = []
            if request.questionnaire_title:
                header_parts.append(f"Questionnaire: {request.questionnaire_title}")
            if request.patient_information:
                pi = request.patient_information
                if pi.full_name:
                    header_parts.append(f"Patient: {pi.full_name}")
                if pi.birth_day:
                    header_parts.append(f"Date of birth: {pi.birth_day}")
            if request.completed_at:
                header_parts.append(f"Completed at: {request.completed_at}")
            header_block = "\n".join(header_parts) if header_parts else ""

            serialized_report = json.dumps(
                [item.model_dump(mode="json", exclude_none=True) for item in request.report],
                indent=2,
            )

            prompt_content = (
                f"User Instructions:\n{instructions}\n\n"
            )
            if header_block:
                prompt_content += f"Context (questionnaire, patient, date):\n{header_block}\n\n"
            prompt_content += f"Patient Report Data:\n{serialized_report}"

            messages = [
                SystemMessage(content=LETTER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content)
            ]

            # Use Langfuse context for letter generation with user tracking
            async with langfuse_context(
                user_id=user_id,
                trace_name="letter.generation",
                tags=["letter", "medical"],
                metadata={"report_item_count": len(request.report)},
            ) as langfuse_handler:
                callbacks = [langfuse_handler] if langfuse_handler else None

                logger.debug("Generating letter content...")

                async for chunk, _ in self.llm_service.generate_stream(
                    messages, callbacks=callbacks
                ):
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

