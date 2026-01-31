"""SQLAlchemy ORM models for chatbot messages."""

from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID, uuid4
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base


class MessageModel(Base):
    """ORM model for messages table."""

    __tablename__ = "chatbot_messages"

    id = Column(
        PG_UUID[UUID](as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    session_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("chatbot_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    message_type = Column(
        String,
        nullable=False,
    )
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    reaction = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False, server_default=text("0"))
    output_tokens = Column(Integer, default=0, nullable=False, server_default=text("0"))
    total_tokens = Column(Integer, default=0, nullable=False, server_default=text("0"))
    message_metadata = Column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    references = Column(
        JSONB,
        default=list,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    # Relationship to session
    session = relationship("SessionModel", back_populates="messages")

    # Check constraint for message_type
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('human', 'ai')",
            name="check_message_type",
        ),
        Index("idx_messages_session_created", "session_id", text("created_at DESC")),
    )

    def __repr__(self) -> str:
        return f"<MessageModel(id={self.id}, session_id={self.session_id}, message_type={self.message_type})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "message_type": self.message_type,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reaction": self.reaction,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "metadata": (
                self.message_metadata if isinstance(self.message_metadata, dict) else {}
            ),
            "references": (
                self.references if isinstance(self.references, list) else []
            ),
        }
