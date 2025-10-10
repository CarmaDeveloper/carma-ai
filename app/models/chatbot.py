"""Chatbot models for conversational SSE streaming chat with memory."""

from typing import Optional
from pydantic import BaseModel, Field


class ChatbotRequest(BaseModel):
    """Request model for chatbot with session management."""

    message: str = Field(..., description="User message to respond to")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity. If not provided, a new session will be created.",
    )
