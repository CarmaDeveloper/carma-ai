"""Chat models for SSE streaming chat."""

from pydantic import BaseModel, Field
from typing import Literal


class ChatRequest(BaseModel):
    """Request model for initiating a streamed chat completion."""

    message: str = Field(..., description="Current user message to respond to")
    stream: Literal[True] = Field(
        default=True,
        description="Whether to stream the response using Server-Sent Events. Must be `true` for this endpoint.",
    )
