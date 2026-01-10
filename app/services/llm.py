"""Stateless LLM service."""

from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from langchain_aws.chat_models import ChatBedrock
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import ModelError
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class ModelConfig(BaseModel):
    """Configuration for LLM model."""

    model_id: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    class Config:
        """Pydantic config."""
        
        frozen = True


class LLMService:
    """Stateless service for LLM interactions."""

    def __init__(self, config: Optional[ModelConfig] = None) -> None:
        """
        Initialize the LLM service.

        Args:
            config: Optional configuration override. If not provided, uses settings.
        """
        self.config = config or ModelConfig()
        
        # Determine effective configuration (fallback to settings if not provided)
        self.provider = self.config.provider or settings.EMBEDDING_PROVIDER  # Using same provider logic as before
        self.region = self.config.region or settings.BEDROCK_REGION
        self.model_id = self.config.model_id or settings.BEDROCK_MODEL
        
        self.max_tokens = self.config.max_tokens if self.config.max_tokens is not None else settings.MODEL_MAX_TOKENS
        self.temperature = self.config.temperature if self.config.temperature is not None else settings.MODEL_TEMPERATURE

    def _create_model(self) -> Any:
        """Create the underlying LangChain model."""
        if self.provider == "bedrock":
            return self._create_bedrock_model()
        else:
            raise ModelError(f"Unsupported model provider: {self.provider}")

    def _create_bedrock_model(self) -> ChatBedrock:
        """Create Bedrock chat model instance."""
        try:
            if not self.model_id:
                raise ModelError("Model ID is required")

            logger.info(
                f"Initializing Bedrock chat model: model={self.model_id}, "
                f"region={self.region}, max_tokens={self.max_tokens}, "
                f"temperature={self.temperature}"
            )

            # Build model kwargs
            model_kwargs = {}
            if self.max_tokens is not None:
                model_kwargs["max_tokens"] = self.max_tokens
            if self.temperature is not None:
                model_kwargs["temperature"] = self.temperature

            return ChatBedrock(
                region_name=self.region,
                model_id=self.model_id,
                model_kwargs=model_kwargs,
            )

        except Exception as e:
            logger.error(f"Failed to create Bedrock model: {str(e)}")
            raise ModelError(f"Failed to initialize Bedrock model: {str(e)}")

    async def generate(
        self, messages: List[BaseMessage]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Generate a complete response from LLM with token usage tracking.

        Args:
            messages: List of conversation messages

        Returns:
            Tuple of (full_response, token_usage_dict_or_none)
        """
        full_response = ""
        token_usage = None

        async for chunk, usage in self.generate_stream(messages):
            if chunk:
                full_response += chunk
            if usage:
                token_usage = usage

        return full_response, token_usage

    async def generate_stream(
        self, messages: List[BaseMessage]
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """
        Stream response from LLM with token usage tracking.

        Args:
            messages: List of conversation messages

        Yields:
            Tuple of (chunk_content, token_usage_dict_or_none)
        """
        try:
            model = self._create_model()
            
            # Variables to capture token usage
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0
            
            # Stream the response
            async for chunk in model.astream(messages):
                content = getattr(chunk, "content", "")
                
                # Only yield content chunks
                if isinstance(content, str) and content:
                    yield content, None
                
                # Capture token usage from usage_metadata if available
                usage_metadata = getattr(chunk, "usage_metadata", None)
                if usage_metadata:
                    input_tokens = usage_metadata.get("input_tokens", 0)
                    output_tokens = usage_metadata.get("output_tokens", 0)
                    total_tokens = usage_metadata.get("total_tokens", 0)
            
            # Yield final token usage
            if total_tokens > 0:
                logger.debug(
                    f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}"
                )
                yield "", {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
                
        except Exception as e:
            logger.error(f"LLM streaming failed: {str(e)}", exc_info=True)
            raise ModelError(f"Failed to stream from LLM: {str(e)}")

