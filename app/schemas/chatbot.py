"""Chatbot models for conversational SSE streaming chat with database persistence."""

from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


class ReactionType(str, Enum):
    """Enum for message reaction types."""

    LIKE = "LIKE"
    DISLIKE = "DISLIKE"


class DocumentReference(BaseModel):
    """Reference to a source document used for RAG context."""

    document_id: str = Field(..., description="Unique identifier of the document chunk")
    file_name: str = Field(..., description="Name of the source file")
    knowledge_id: str = Field(
        ..., description="Knowledge base ID the document belongs to"
    )
    source_url: Optional[str] = Field(
        default=None, description="S3 URL or path to the source file"
    )
    relevance_score: Optional[float] = Field(
        default=None, description="Similarity score from vector search"
    )


class ChatbotRequest(BaseModel):
    """Request model for chatbot with session management and optional RAG."""

    message: str = Field(..., description="User message to respond to")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity. If not provided, a new session will be created.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata to store with session/messages",
    )

    # RAG configuration
    use_rag: Optional[bool] = Field(
        default=True,
        description="Whether to use RAG for context retrieval. Defaults to True.",
    )
    knowledge_id: Optional[str] = Field(
        default=None,
        description="Knowledge base ID for RAG context retrieval. "
        "If None and use_rag is True, searches across ALL knowledge bases.",
    )


class PaginationMetadata(BaseModel):
    """Pagination metadata for list responses."""

    page: int = Field(..., description="Current page number (1-indexed)")
    per_page: int = Field(..., description="Number of items per page")
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")


class MessageResponse(BaseModel):
    """Response model for a single message."""

    id: UUID = Field(..., description="Message ID (UUID)")
    session_id: UUID = Field(..., description="Session ID (UUID)")
    message_type: str = Field(..., description="Message type: 'human' or 'ai'")
    content: str = Field(..., description="Message content")
    created_at: str = Field(..., description="Message creation timestamp (ISO format)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Message metadata"
    )


class SessionResponse(BaseModel):
    """Response model for a session."""

    session_id: UUID = Field(..., description="Unique session identifier (UUID)")
    user_id: Optional[str] = Field(None, description="User identifier if available")
    title: Optional[str] = Field(
        None, description="Session title (first 50 characters of first message)"
    )
    created_at: str = Field(..., description="Session creation timestamp (ISO format)")
    last_accessed_at: str = Field(..., description="Last access timestamp (ISO format)")
    is_active: bool = Field(..., description="Whether session is active")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Session metadata"
    )


class SessionHistoryResponse(BaseModel):
    """Response model for session history with page-based pagination."""

    session: SessionResponse = Field(..., description="Session information")
    messages: List[MessageResponse] = Field(
        ..., description="List of messages in chronological order"
    )
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


class SessionListResponse(BaseModel):
    """Response model for list of sessions with page-based pagination."""

    sessions: List[SessionResponse] = Field(..., description="List of sessions")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


class SessionStatsResponse(BaseModel):
    """Response model for session statistics."""

    sessions: Dict[str, int] = Field(
        ...,
        description="Session statistics (total, active, inactive, unique_users)",
    )
    messages: Dict[str, Any] = Field(
        ..., description="Message statistics (total, human, ai, avg_per_session)"
    )


class DeleteSessionResponse(BaseModel):
    """Response model for session deletion."""

    session_id: UUID = Field(..., description="Deleted session ID (UUID)")
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Result message")


class AddMessageReactionRequest(BaseModel):
    """Request model for adding a reaction to a message."""

    reaction_type: ReactionType = Field(
        ..., description="Type of reaction: 'LIKE' or 'DISLIKE'"
    )


class MessageReactionResponse(BaseModel):
    """Response model for message reaction operation."""

    message_id: UUID = Field(..., description="Message ID (UUID)")
    session_id: UUID = Field(..., description="Session ID (UUID)")
    reaction: Optional[ReactionType] = Field(
        default=None, description="Reaction type (LIKE or DISLIKE)"
    )
    success: bool = Field(..., description="Whether operation was successful")
    message: str = Field(..., description="Result message")
