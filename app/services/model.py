"""LLM model service for text generation."""

from langchain_community.chat_models import BedrockChat

from app.core.config import settings
from app.core.exceptions import ModelError
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class ModelService:
    """Service for LLM text generation."""

    def __init__(self) -> None:
        """Initialize model service."""
        self.provider = (
            settings.EMBEDDING_PROVIDER
        )  # Using same provider for consistency
        self._model = None

    def get_model(self):
        """Get the LLM model instance."""
        if self._model is None:
            self._model = self._create_model()
        return self._model

    def _create_model(self):
        """Create model based on provider."""
        if self.provider == "bedrock":
            return self._create_bedrock_model()
        else:
            raise ModelError(f"Unsupported model provider: {self.provider}")

    def _create_bedrock_model(self):
        """Create Bedrock chat model instance."""
        try:
            if not settings.BEDROCK_MODEL:
                raise ModelError("BEDROCK_MODEL setting is required")

            logger.info(
                f"Initializing Bedrock chat model: model={settings.BEDROCK_MODEL}, "
                f"region={settings.BEDROCK_REGION}, max_tokens={settings.MODEL_MAX_TOKENS}, "
                f"temperature={settings.MODEL_TEMPERATURE}"
            )

            # Build model kwargs based on what's configured
            model_kwargs = {}

            # Only add parameters if they are explicitly set
            if settings.MODEL_MAX_TOKENS is not None:
                model_kwargs["max_tokens"] = settings.MODEL_MAX_TOKENS
            if settings.MODEL_TEMPERATURE is not None:
                model_kwargs["temperature"] = settings.MODEL_TEMPERATURE

            logger.info(f"Model kwargs: {model_kwargs}")

            return BedrockChat(
                region_name=settings.BEDROCK_REGION,
                model_id=settings.BEDROCK_MODEL,
                model_kwargs=model_kwargs,
            )

        except Exception as e:
            logger.error(f"Failed to create Bedrock model: {str(e)}")
            raise ModelError(f"Failed to initialize Bedrock model: {str(e)}")


# Singleton instance
model_service = ModelService()
