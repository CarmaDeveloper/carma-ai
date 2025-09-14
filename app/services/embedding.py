"""Embedding service for vector embeddings."""

from langchain_aws import BedrockEmbeddings

from app.core.config import settings
from app.core.exceptions import ModelError
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings."""

    def __init__(self) -> None:
        """Initialize embedding service."""
        self.provider = settings.EMBEDDING_PROVIDER
        self._embedding_model = None

    def get_embedding_model(self):
        """Get the embedding model instance."""
        if self._embedding_model is None:
            self._embedding_model = self._create_embedding_model()
        return self._embedding_model

    def _create_embedding_model(self):
        """Create embedding model based on provider."""
        if self.provider == "bedrock":
            return self._create_bedrock_embeddings()
        else:
            raise ModelError(f"Unsupported embedding provider: {self.provider}")

    def _create_bedrock_embeddings(self):
        """Create Bedrock embeddings instance."""
        try:
            if not settings.BEDROCK_EMBEDDING:
                raise ModelError("BEDROCK_EMBEDDING setting is required")

            logger.info(
                f"Initializing Bedrock embeddings: model={settings.BEDROCK_EMBEDDING}, "
                f"region={settings.BEDROCK_REGION}"
            )

            return BedrockEmbeddings(
                region_name=settings.BEDROCK_REGION,
                model_id=settings.BEDROCK_EMBEDDING,
            )

        except Exception as e:
            logger.error(f"Failed to create Bedrock embeddings: {str(e)}")
            raise ModelError(f"Failed to initialize Bedrock embeddings: {str(e)}")


# Singleton instance
embedding_service = EmbeddingService()
