"""Dependency injection functions for chatbot service."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories import (
    SessionRepository,
    MessageRepository,
    DocumentRecordRepository,
)
from app.services.chatbot import ChatbotService


def get_session_repository(
    session: AsyncSession = Depends(get_db),
) -> SessionRepository:
    """Get session repository instance."""
    return SessionRepository(session)


def get_message_repository(
    session: AsyncSession = Depends(get_db),
) -> MessageRepository:
    """Get message repository instance."""
    return MessageRepository(session)


def get_document_record_repository(
    session: AsyncSession = Depends(get_db),
) -> DocumentRecordRepository:
    """Get document record repository instance."""
    return DocumentRecordRepository(session)


def get_chatbot_service(
    session_repo: SessionRepository = Depends(get_session_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    document_record_repo: DocumentRecordRepository = Depends(
        get_document_record_repository
    ),
) -> ChatbotService:
    """Get chatbot service instance with injected repositories."""
    return ChatbotService(
        session_repo=session_repo,
        message_repo=message_repo,
        document_record_repo=document_record_repo,
    )
