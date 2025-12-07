"""Dependency injection functions for ingestion service."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories import DocumentRecordRepository
from app.services.ingestion import IngestionService


def get_document_record_repository(
    session: AsyncSession = Depends(get_db),
) -> DocumentRecordRepository:
    """Get document record repository instance."""
    return DocumentRecordRepository(session)


def get_ingestion_service(
    document_record_repo: DocumentRecordRepository = Depends(
        get_document_record_repository
    ),
) -> IngestionService:
    """Get ingestion service instance with injected repositories."""
    return IngestionService(
        document_record_repo=document_record_repo,
    )
