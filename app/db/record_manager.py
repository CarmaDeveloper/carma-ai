"""Record manager service for tracking document chunks and file relationships."""

from typing import List, Optional

import asyncpg

from app.core.config import settings
from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class RecordManagerService:
    """Service for managing document records and file relationships."""

    def __init__(self, table_name: str = "document_records") -> None:
        """Initialize record manager service."""
        self.table_name = table_name
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def get_pool(self) -> asyncpg.Pool:
        """Get or create database connection pool."""
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    database=settings.POSTGRES_DB,
                    min_size=1,
                    max_size=10,
                )
                logger.info("Successfully created database connection pool")
            except Exception as e:
                logger.error(
                    f"Failed to create database connection pool: {e}. "
                    f"Database: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )
                raise VectorStoreError(f"Database connection failed: {e}")

        return self._pool

    async def _initialize_table(self) -> None:
        """Ensure the records table exists."""
        if self._initialized:
            return

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    filename TEXT NOT NULL,
                    knowledge_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (filename, knowledge_id, document_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_filename 
                ON {self.table_name} (filename);
                
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_knowledge_id 
                ON {self.table_name} (knowledge_id);
                
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_document_id 
                ON {self.table_name} (document_id);
            """
            )

        self._initialized = True
        logger.info(f"Initialized records table: {self.table_name}")

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
        await self._initialize_table()

        if not document_ids:
            logger.warning(f"No document IDs provided for file: {filename}")
            return

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            # Use a transaction to ensure all records are added atomically
            async with connection.transaction():
                # First, remove any existing records for this file
                await connection.execute(
                    f"DELETE FROM {self.table_name} WHERE filename = $1 AND knowledge_id = $2",
                    filename,
                    knowledge_id,
                )

                # Then add the new records
                records = [(filename, knowledge_id, doc_id) for doc_id in document_ids]
                await connection.executemany(
                    f"INSERT INTO {self.table_name} (filename, knowledge_id, document_id) VALUES ($1, $2, $3)",
                    records,
                )

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
        await self._initialize_table()

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            # Get the document IDs before deleting
            result = await connection.fetch(
                f"SELECT document_id FROM {self.table_name} WHERE filename = $1 AND knowledge_id = $2",
                filename,
                knowledge_id,
            )

            document_ids = [row["document_id"] for row in result]

            if document_ids:
                # Delete the records
                await connection.execute(
                    f"DELETE FROM {self.table_name} WHERE filename = $1 AND knowledge_id = $2",
                    filename,
                    knowledge_id,
                )

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
        await self._initialize_table()

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            result = await connection.fetch(
                f"SELECT document_id FROM {self.table_name} WHERE filename = $1 AND knowledge_id = $2",
                filename,
                knowledge_id,
            )

        document_ids = [row["document_id"] for row in result]
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
        await self._initialize_table()

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            result = await connection.fetch(
                f"SELECT DISTINCT filename FROM {self.table_name} WHERE knowledge_id = $1",
                knowledge_id,
            )

        filenames = [row["filename"] for row in result]
        logger.debug(f"Found {len(filenames)} files in knowledge base: {knowledge_id}")

        return filenames

    async def get_knowledge_base_stats(self, knowledge_id: str) -> dict:
        """
        Get statistics for a knowledge base.

        Args:
            knowledge_id: Knowledge base identifier

        Returns:
            Dictionary with stats (total_files, total_documents, files)
        """
        await self._initialize_table()

        pool = await self.get_pool()
        async with pool.acquire() as connection:
            # Get file count and document count in one query
            result = await connection.fetchrow(
                f"""
                SELECT 
                    COUNT(DISTINCT filename) as file_count,
                    COUNT(document_id) as document_count
                FROM {self.table_name} 
                WHERE knowledge_id = $1
                """,
                knowledge_id,
            )

            # Get list of files
            files_result = await connection.fetch(
                f"SELECT DISTINCT filename FROM {self.table_name} WHERE knowledge_id = $1",
                knowledge_id,
            )

        files = [row["filename"] for row in files_result]

        stats = {
            "total_files": result["file_count"] if result else 0,
            "total_documents": result["document_count"] if result else 0,
            "files": files,
        }

        logger.debug(f"Knowledge base stats for {knowledge_id}: {stats}")
        return stats

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Closed record manager database connection pool")


# Singleton instance
record_manager_service = RecordManagerService()
