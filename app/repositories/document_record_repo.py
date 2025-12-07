"""Repository for DocumentRecordModel database operations with Protocol."""

from typing import List, Dict, Any, Protocol
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_record import DocumentRecordModel
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class DocumentRecordRepositoryProtocol(Protocol):
    """Protocol for DocumentRecordRepository interface."""

    async def add_file_records(
        self, filename: str, document_ids: List[str], knowledge_id: str
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


class DocumentRecordRepository:
    """Repository for DocumentRecordModel operations with injected session."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def add_file_records(
        self, filename: str, document_ids: List[str], knowledge_id: str
    ) -> None:
        """
        Add document records for a file.

        Args:
            filename: Name of the source file
            document_ids: List of document chunk IDs generated from the file
            knowledge_id: Knowledge base identifier
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
                knowledge_id=knowledge_id,
                document_id=doc_id,
            )
            for doc_id in document_ids
        ]
        self.session.add_all(records)
        await self.session.commit()

        logger.info(
            f"Added {len(document_ids)} document records for file: {filename}, "
            f"knowledge_id: {knowledge_id}"
        )

    async def remove_file_records(self, filename: str, knowledge_id: str) -> List[str]:
        """
        Remove all document records for a file.

        Args:
            filename: Name of the source file
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
            filename: Name of the source file
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
        Get all filenames in a knowledge base.

        Args:
            knowledge_id: Knowledge base identifier

        Returns:
            List of unique filenames in the knowledge base
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
