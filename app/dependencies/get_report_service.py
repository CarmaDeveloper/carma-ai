"""Dependency injection functions for report service."""

from fastapi import Depends

from app.dependencies.get_ingestion_service import get_document_record_repository
from app.repositories import DocumentRecordRepository
from app.services.report import ReportGenerationService


def get_report_service(
    document_record_repo: DocumentRecordRepository = Depends(
        get_document_record_repository
    ),
) -> ReportGenerationService:
    """Get report generation service instance with injected repositories."""
    return ReportGenerationService(
        document_record_repo=document_record_repo,
    )

