"""Application configuration."""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    APP_NAME: str = Field(default="Carma AI", env="APP_NAME")
    DOCS_PORT: int = Field(default=8000, env="DOCS_PORT")

    # PostgreSQL settings
    POSTGRES_USER: str = Field(default="postgres", env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="postgres", env="POSTGRES_PASSWORD")
    POSTGRES_HOST: str = Field(default="localhost", env="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, env="POSTGRES_PORT")
    POSTGRES_DB: str = Field(default="carma_ai", env="POSTGRES_DB")

    @property
    def DATABASE_URL(self) -> str:
        """Construct DATABASE_URL from individual PostgreSQL parameters."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Vector Store settings
    VECTOR_STORE_PROVIDER: str = Field(default="pg-vector", env="VECTOR_STORE_PROVIDER")

    # Embedding settings
    EMBEDDING_PROVIDER: str = Field(default="bedrock", env="EMBEDDING_PROVIDER")

    # Model settings
    MODEL_MAX_TOKENS: Optional[int] = Field(default=None, env="MODEL_MAX_TOKENS")
    MODEL_TEMPERATURE: Optional[float] = Field(
        default=None, env="MODEL_TEMPERATURE", ge=0, le=1
    )

    # AWS Bedrock settings
    BEDROCK_REGION: str = Field(default="ca-central-1", env="BEDROCK_REGION")
    BEDROCK_EMBEDDING: Optional[str] = Field(
        default="amazon.titan-embed-text-v2:0", env="BEDROCK_EMBEDDING"
    )
    BEDROCK_MODEL: Optional[str] = Field(
        default="anthropic.claude-3-sonnet-20240229-v1:0", env="BEDROCK_MODEL"
    )

    # AWS S3 settings
    S3_BUCKET_NAME: str = Field(default="carma-bucket", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="ca-central-1", env="S3_REGION")

    # AWS Comprehend settings
    COMPREHEND_REGION: str = Field(default="ca-central-1", env="COMPREHEND_REGION")
    COMPREHEND_THRESHOLD: float = Field(
        default=0.9, env="COMPREHEND_THRESHOLD", ge=0, le=1
    )
    COMPREHEND_TYPES: list[str] = Field(
        default=["LOCATION", "PERSON"], env="COMPREHEND_TYPES"
    )

    # Authentication settings
    AUTH_TOKEN: str = Field(default="", env="AUTH_TOKEN")

    # CORS settings
    CORS_ORIGINS: list[str] = Field(default=["*"], env="CORS_ORIGINS")

    # Ingestion settings
    CHUNK_SIZE: int = Field(default=1000, env="CHUNK_SIZE", ge=100, le=4000)
    CHUNK_OVERLAP: int = Field(default=200, env="CHUNK_OVERLAP", ge=0, le=1000)
    MAX_FILE_SIZE: int = Field(default=50 * 1024 * 1024, env="MAX_FILE_SIZE")  # 50MB

    # Chatbot session settings
    CHATBOT_CLEANUP_INTERVAL_SECONDS: int = Field(
        default=60 * 60, env="CHATBOT_CLEANUP_INTERVAL_SECONDS", ge=30, le=3600
    )  # Run cleanup every 1 hour by default
    # Chatbot persistence settings
    CHATBOT_SESSION_RETENTION_DAYS: int = Field(
        default=90, env="CHATBOT_SESSION_RETENTION_DAYS", ge=1, le=365
    )  # Number of days to retain inactive sessions
    CHATBOT_MESSAGE_HISTORY_LIMIT: int = Field(
        default=50, env="CHATBOT_MESSAGE_HISTORY_LIMIT", ge=10, le=500
    )  # Max messages to load from history

    # RAG (Retrieval-Augmented Generation) settings
    RAG_DEFAULT_K: int = Field(
        default=4, env="RAG_DEFAULT_K", ge=1, le=10
    )  # Default number of documents to retrieve per query
    RAG_DEFAULT_SCORE_THRESHOLD: Optional[float] = Field(
        default=None, env="RAG_DEFAULT_SCORE_THRESHOLD", ge=0.0, le=1.0
    )  # Default minimum similarity score (None = no filtering)
    RAG_MAX_CONTEXT_LENGTH: int = Field(
        default=6000, env="RAG_MAX_CONTEXT_LENGTH", ge=500, le=32000
    )  # Max character length for context (roughly ~1500 tokens)
    RAG_INCLUDE_HISTORY_QUERIES: bool = Field(
        default=True, env="RAG_INCLUDE_HISTORY_QUERIES"
    )  # Whether to use conversation history for additional search queries
    RAG_MAX_HISTORY_QUERIES: int = Field(
        default=2, env="RAG_MAX_HISTORY_QUERIES", ge=0, le=5
    )  # Max number of history messages to use as search queries

    # Environment
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    LOG_LEVEL: str = Field(default="DEBUG", env="LOG_LEVEL")
    DEBUG: bool = Field(default=True, env="DEBUG")

    class Config:
        env_file = ".env"


settings = Settings()
