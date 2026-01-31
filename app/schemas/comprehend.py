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
        json_schema_extra = {
            "example": {
                "texts": [
                    "My username is john_doe and my password is secret123.",
                    "Credit card number: 4532-1234-5678-9012, PIN: 1234.",
                    "Bank account number is 123456789012.",
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
        json_schema_extra = {
            "example": {
                "redacted_texts": [
                    "My username is [REDACTED] and my password is [REDACTED].",
                    "Credit card number: [REDACTED], PIN: [REDACTED].",
                    "Bank account number is [REDACTED].",
                ],
                "processed_count": 3,
            }
        }
