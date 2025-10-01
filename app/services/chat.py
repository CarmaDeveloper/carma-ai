"""Chat service providing SSE streaming responses using Bedrock."""

from typing import AsyncGenerator

from app.core.logging import setup_logger
from app.services.model import model_service

logger = setup_logger(__name__)


class ChatService:
    """Service to handle chat interactions and streaming generation."""

    async def stream_chat(self, *, message: str) -> AsyncGenerator[str, None]:
        """
        Stream an assistant reply using Server-Sent Events (SSE).

        This method constructs a minimal prompt from the provided user message and
        streams model output incrementally as SSE data frames.

        Args:
            message: The user's input message to respond to.

        Yields:
            An async generator yielding SSE-formatted strings where each chunk is
            prefixed with "data: " and terminated by a blank line ("\n\n").
            The final frame is "data: [DONE]\n\n".

        Raises:
            Exception: Any underlying model or streaming error will be logged and
            surfaced via an SSE error frame.
        """
        # Build a minimal prompt: user message followed by assistant cue
        final_prompt = f"User: {message}\nAssistant:"

        # Get model and stream tokens
        model = model_service.get_model()

        try:
            async for chunk in model.astream(final_prompt):
                text = getattr(chunk, "content", None) or str(chunk)
                lines = text.splitlines()
                if lines:
                    for line in lines:
                        yield f"data: {line}\n"
                    yield "\n"
            # signal end of stream
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield "data: [ERROR] Failed to stream chat response\n\n"


# Singleton instance
chat_service = ChatService()
