"""SQLAlchemy ORM models for document records."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy import (
    Column,
    Text,
    DateTime,
    Index,
    text,
    PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


class DocumentRecordModel(Base):
    """ORM model for document_records table."""

    __tablename__ = "document_records"

    filename = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    knowledge_id = Column(Text, nullable=False)
    document_id = Column(Text, nullable=False)
    sub_references = Column(
        JSONB,
        nullable=True,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Composite primary key
    __table_args__ = (
        PrimaryKeyConstraint("filename", "knowledge_id", "document_id"),
        Index("idx_document_records_knowledge_id", "knowledge_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentRecordModel(filename={self.filename}, title={self.title}, "
            f"knowledge_id={self.knowledge_id}, document_id={self.document_id})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert document record to dictionary."""
        return {
            "filename": self.filename,
            "title": self.title,
            "knowledge_id": self.knowledge_id,
            "document_id": self.document_id,
            "sub_references": self.sub_references or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
