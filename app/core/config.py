"""Application configuration."""

import os
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    APP_NAME: str = "Carma AI"

    # Server settings

    # PostgreSQL settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "carma_ai")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
    )

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
    COMPREHEND_TYPES: List[str] = Field(
        default=["LOCATION", "PERSON"], env="COMPREHEND_TYPES"
    )

    # Authentication settings
    AUTH_TOKEN: str = Field(default="", env="AUTH_TOKEN")

    # CORS settings
    CORS_ORIGINS: list = ["*"]  # For production, replace with specific origins

    # Ingestion settings
    CHUNK_SIZE: int = Field(default=1000, env="CHUNK_SIZE", ge=100, le=4000)
    CHUNK_OVERLAP: int = Field(default=200, env="CHUNK_OVERLAP", ge=0, le=1000)
    MAX_FILE_SIZE: int = Field(default=50 * 1024 * 1024, env="MAX_FILE_SIZE")  # 50MB

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    DEBUG: bool = os.getenv("DEBUG", True)

    class Config:
        env_file = ".env"


settings = Settings()
