"""Comprehend service models."""

from typing import List

from pydantic import BaseModel, Field


class ComprehendRequest(BaseModel):
    """Request model for PII redaction using AWS Comprehend."""

    texts: List[str] = Field(
        ...,
        description="List of text strings to process for PII redaction",
        min_items=1,
        max_items=1000,
    )

    class Config:
        schema_extra = {
            "example": {
                "texts": [
                    "Hello, my name is John Smith and I live in New York.",
                    "Contact me at john.smith@email.com or call 555-123-4567.",
                    "My social security number is 123-45-6789.",
                ]
            }
        }


class ComprehendResponse(BaseModel):
    """Response model for PII redaction using AWS Comprehend."""

    redacted_texts: List[str] = Field(
        ..., description="List of texts with PII redacted"
    )
    processed_count: int = Field(..., description="Number of texts processed")

    class Config:
        schema_extra = {
            "example": {
                "redacted_texts": [
                    "Hello, my name is [REDACTED] and I live in [REDACTED].",
                    "Contact me at [REDACTED] or call [REDACTED].",
                    "My social security number is [REDACTED].",
                ],
                "processed_count": 3,
            }
        }
