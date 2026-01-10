"""Service for generating templates via LLM streaming."""

import json
from typing import AsyncGenerator, Dict, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import setup_logger
from app.services.llm import LLMService
from app.prompts.template import TEMPLATE_TITLE_SYSTEM_PROMPT, TEMPLATE_CONTENT_SYSTEM_PROMPT

logger = setup_logger(__name__)


class TemplateService:
    """Service to handle template generation with SSE streaming."""

    def __init__(self, llm_service: LLMService):
        """
        Initialize the template service.

        Args:
            llm_service: Service for LLM interactions
        """
        self.llm_service = llm_service

    async def stream_template_generation(
        self, prompt: str
    ) -> AsyncGenerator[tuple[str, dict], None]:
        """
        Generate template title and content from a prompt and stream as events.

        Args:
            prompt: User provided prompt description

        Yields:
            Tuples of (event_type, data_dict)
        """
        logger.info(f"Starting template generation for prompt: {prompt[:50]}...")

        yield ("template.init", {"status": "started", "prompt": prompt})

        try:
            messages = [
                SystemMessage(content=TEMPLATE_TITLE_SYSTEM_PROMPT),
                HumanMessage(content=f"Generate a title for a template based on this description: {prompt}")
            ]

            full_title = ""
            async for chunk, _ in self.llm_service.generate_stream(messages):
                if chunk:
                    full_title += chunk
                    yield ("template.title", {"content": chunk})
            
            logger.debug(f"Title generated: {full_title}")

        except Exception as e:
            logger.error(f"Error generating title: {e}", exc_info=True)
            yield ("template.error", {"error": str(e), "message": "Failed to generate title"})
            return

        try:
            logger.debug("Generating template content...")
            messages = [
                SystemMessage(content=TEMPLATE_CONTENT_SYSTEM_PROMPT),
                HumanMessage(content=f"Create a markdown template for: {full_title}\n\nUser description: {prompt}")
            ]

            async for chunk, _ in self.llm_service.generate_stream(messages):
                if chunk:
                    yield ("template.content", {"content": chunk})

        except Exception as e:
            logger.error(f"Error generating content: {e}", exc_info=True)
            yield ("template.error", {"error": str(e), "message": "Failed to generate content"})
            return

        yield ("template.complete", {"status": "complete"})
        logger.info("Template generation completed.")

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
