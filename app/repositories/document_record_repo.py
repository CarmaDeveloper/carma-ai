"""Repository for DocumentRecordModel database operations with Protocol."""

from typing import List, Dict, Any, Protocol, Optional
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_record import DocumentRecordModel
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class DocumentRecordRepositoryProtocol(Protocol):
    """Protocol for DocumentRecordRepository interface."""

    async def add_file_records(
        self,
        filename: str,
        document_ids: List[str],
        knowledge_id: str,
        title: str,
        sub_references: Optional[List[Dict[str, str]]] = None,
    ) -> None: ...

    async def remove_file_records(
        self, filename: str, knowledge_id: str
    ) -> List[str]: ...

    async def get_file_document_ids(
        self, filename: str, knowledge_id: str
    ) -> List[str]: ...

    async def get_knowledge_base_files(self, knowledge_id: str) -> List[str]: ...

    async def get_knowledge_base_stats(self, knowledge_id: str) -> Dict[str, Any]: ...

    async def get_all_knowledge_ids(self) -> List[str]: ...

    async def get_file_info_by_filenames(
        self, filenames: List[str], knowledge_id: str
    ) -> List[Dict[str, Any]]: ...

    async def update_document_metadata(
        self,
        knowledge_id: str,
        filename: str,
        title: str,
        sub_references: List[Dict[str, str]],
    ) -> int: ...

    async def file_exists(self, filename: str, knowledge_id: str) -> bool: ...


class DocumentRecordRepository:
    """Repository for DocumentRecordModel operations with injected session."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def add_file_records(
        self,
        filename: str,
        document_ids: List[str],
        knowledge_id: str,
        title: str,
        sub_references: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """
        Add document records for a file.

        Args:
            filename: Name of the file in S3 bucket (e.g., 'report_2024.pdf')
            document_ids: List of document chunk IDs generated from the file
            knowledge_id: Knowledge base identifier
            title: User-defined display title for the document (e.g., 'Annual Report 2024')
            sub_references: Optional list of sub-reference dicts with 'title' and 'link' keys
        """
        if not document_ids:
            logger.warning(f"No document IDs provided for file: {filename}")
            return

        # First, remove any existing records for this file
        await self.session.execute(
            delete(DocumentRecordModel).where(
                DocumentRecordModel.filename == filename,
                DocumentRecordModel.knowledge_id == knowledge_id,
            )
        )

        # Then add the new records
        records = [
            DocumentRecordModel(
                filename=filename,
                title=title,
                knowledge_id=knowledge_id,
                document_id=doc_id,
                sub_references=sub_references or [],
            )
            for doc_id in document_ids
        ]
        self.session.add_all(records)
        await self.session.commit()

        logger.info(
            f"Added {len(document_ids)} document records for file: {filename}, "
            f"title: {title}, knowledge_id: {knowledge_id}"
        )

    async def remove_file_records(self, filename: str, knowledge_id: str) -> List[str]:
        """
        Remove all document records for a file.

        Args:
            filename: Name of the file in S3 bucket
            knowledge_id: Knowledge base identifier

        Returns:
            List of document IDs that were removed
        """
        # Get the document IDs before deleting
        result = await self.session.execute(
            select(DocumentRecordModel.document_id).where(
                DocumentRecordModel.filename == filename,
                DocumentRecordModel.knowledge_id == knowledge_id,
            )
        )
        document_ids = list(result.scalars().all())

        if document_ids:
            # Delete the records
            await self.session.execute(
                delete(DocumentRecordModel).where(
                    DocumentRecordModel.filename == filename,
                    DocumentRecordModel.knowledge_id == knowledge_id,
                )
            )
            await self.session.commit()

            logger.info(
                f"Removed {len(document_ids)} document records for file: {filename}, "
                f"knowledge_id: {knowledge_id}"
            )
        else:
            logger.warning(
                f"No records found for file: {filename}, knowledge_id: {knowledge_id}"
            )

        return document_ids

    async def get_file_document_ids(
        self, filename: str, knowledge_id: str
    ) -> List[str]:
        """
        Get all document IDs for a specific file.

        Args:
            filename: Name of the file in S3 bucket
            knowledge_id: Knowledge base identifier

        Returns:
            List of document IDs associated with the file
        """
        result = await self.session.execute(
            select(DocumentRecordModel.document_id).where(
                DocumentRecordModel.filename == filename,
                DocumentRecordModel.knowledge_id == knowledge_id,
            )
        )
        document_ids = list(result.scalars().all())
        logger.debug(f"Found {len(document_ids)} document IDs for file: {filename}")

        return document_ids

    async def get_knowledge_base_files(self, knowledge_id: str) -> List[str]:
        """
        Get all filenames (S3 file names) in a knowledge base.

        Args:
            knowledge_id: Knowledge base identifier

        Returns:
            List of unique S3 filenames in the knowledge base
        """
        result = await self.session.execute(
            select(DocumentRecordModel.filename)
            .where(DocumentRecordModel.knowledge_id == knowledge_id)
            .distinct()
        )
        filenames = list(result.scalars().all())
        logger.debug(f"Found {len(filenames)} files in knowledge base: {knowledge_id}")

        return filenames

    async def get_knowledge_base_stats(self, knowledge_id: str) -> Dict[str, Any]:
        """
        Get statistics for a knowledge base.

        Args:
            knowledge_id: Knowledge base identifier

        Returns:
            Dictionary with stats (total_files, total_documents, files)
        """
        # Get file count and document count in one query
        stats_query = select(
            func.count(func.distinct(DocumentRecordModel.filename)).label("file_count"),
            func.count(DocumentRecordModel.document_id).label("document_count"),
        ).where(DocumentRecordModel.knowledge_id == knowledge_id)

        result = await self.session.execute(stats_query)
        stats_row = result.first()

        # Get list of files
        files_result = await self.session.execute(
            select(DocumentRecordModel.filename)
            .where(DocumentRecordModel.knowledge_id == knowledge_id)
            .distinct()
        )
        files = list(files_result.scalars().all())

        stats = {
            "total_files": stats_row.file_count if stats_row else 0,
            "total_documents": stats_row.document_count if stats_row else 0,
            "files": files,
        }

        logger.debug(f"Knowledge base stats for {knowledge_id}: {stats}")
        return stats

    async def get_all_knowledge_ids(self) -> List[str]:
        """
        Get all unique knowledge base IDs that have documents.

        Returns:
            List of unique knowledge base identifiers
        """
        result = await self.session.execute(
            select(DocumentRecordModel.knowledge_id).distinct()
        )
        knowledge_ids = list(result.scalars().all())
        logger.debug(f"Found {len(knowledge_ids)} knowledge bases")
        return knowledge_ids

    async def get_file_info_by_filenames(
        self, filenames: List[str], knowledge_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get file info (filename, title, and sub_references) for a list of filenames.

        Args:
            filenames: List of S3 filenames to look up
            knowledge_id: Knowledge base identifier

        Returns:
            List of dicts with 'filename', 'title', and 'sub_references' keys for each unique file
        """
        if not filenames:
            return []

        result = await self.session.execute(
            select(
                DocumentRecordModel.filename,
                DocumentRecordModel.title,
                DocumentRecordModel.sub_references,
            )
            .where(
                DocumentRecordModel.filename.in_(filenames),
                DocumentRecordModel.knowledge_id == knowledge_id,
            )
            .distinct()
        )
        rows = result.all()

        file_info = [
            {
                "filename": row.filename,
                "title": row.title,
                "sub_references": row.sub_references or [],
            }
            for row in rows
        ]
        logger.debug(
            f"Found file info for {len(file_info)} files in knowledge base: {knowledge_id}"
        )

        return file_info

    async def update_document_metadata(
        self,
        knowledge_id: str,
        filename: str,
        title: str,
        sub_references: List[Dict[str, str]],
    ) -> int:
        """
        Update the title and sub-references for all records of a document.

        Args:
            knowledge_id: Knowledge base identifier
            filename: Name of the file in S3 bucket
            title: New display title for the document
            sub_references: New list of sub-reference dicts with 'title' and 'link' keys

        Returns:
            Number of rows updated
        """
        result = await self.session.execute(
            update(DocumentRecordModel)
            .where(
                DocumentRecordModel.knowledge_id == knowledge_id,
                DocumentRecordModel.filename == filename,
            )
            .values(title=title, sub_references=sub_references)
        )
        await self.session.commit()

        updated_count = result.rowcount
        logger.info(
            f"Updated {updated_count} document records for file: {filename}, "
            f"knowledge_id: {knowledge_id}, new title: {title}, "
            f"sub_references count: {len(sub_references)}"
        )

        return updated_count

    async def file_exists(self, filename: str, knowledge_id: str) -> bool:
        """
        Check if any document records exist for a given file.

        Args:
            filename: Name of the file in S3 bucket
            knowledge_id: Knowledge base identifier

        Returns:
            True if at least one record exists, False otherwise
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(DocumentRecordModel)
            .where(
                DocumentRecordModel.filename == filename,
                DocumentRecordModel.knowledge_id == knowledge_id,
            )
        )
        count = result.scalar() or 0
        exists = count > 0
        logger.debug(
            f"File exists check: filename={filename}, "
            f"knowledge_id={knowledge_id}, exists={exists}"
        )
        return exists
