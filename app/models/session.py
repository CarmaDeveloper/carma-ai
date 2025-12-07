"""SQLAlchemy ORM models for chatbot sessions."""

from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base


class SessionModel(Base):
    """ORM model for sessions table."""

    __tablename__ = "chatbot_sessions"

    session_id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    user_id = Column(String, nullable=True, index=True)
    title = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_accessed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    session_metadata = Column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Relationship to messages
    messages = relationship(
        "MessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # Indexes
    __table_args__ = (
        Index("idx_chatbot_sessions_user_id", "user_id"),
        Index("idx_chatbot_sessions_last_accessed", "last_accessed_at"),
        Index(
            "idx_chatbot_sessions_active",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SessionModel(session_id={self.session_id}, user_id={self.user_id}, is_active={self.is_active})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": str(self.session_id),
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
            "is_active": self.is_active,
            "metadata": (
                self.session_metadata if isinstance(self.session_metadata, dict) else {}
            ),
        }
