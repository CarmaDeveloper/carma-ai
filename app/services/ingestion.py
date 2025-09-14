"""Main ingestion service for document processing pipeline."""

import uuid
from typing import List

from langchain_core.documents import Document

from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger
from app.db.record_manager import record_manager_service
from app.models.ingestion import (
    IngestionRequest,
    IngestionResponse,
    IngestionStatusResponse,
    DocumentRemovalResponse,
)
from app.services.document_loader import document_loader_service
from app.services.embedding import embedding_service
from app.services.s3 import s3_service
from app.services.text_splitter import text_splitter_service
from app.services.vector_store import vector_store_service

logger = setup_logger(__name__)


class IngestionService:
    """Main service for document ingestion pipeline."""

    def __init__(self) -> None:
        """Initialize ingestion service."""
        self.document_loader = document_loader_service
        self.text_splitter = text_splitter_service
        self.embedding_service = embedding_service
        self.vector_store = vector_store_service
        self.record_manager = record_manager_service

    def generate_document_ids(self, count: int) -> List[str]:
        """
        Generate unique document IDs.

        Args:
            count: Number of IDs to generate

        Returns:
            List of unique UUIDs
        """
        return [str(uuid.uuid4()) for _ in range(count)]

    async def ingest_document(self, request: IngestionRequest) -> IngestionResponse:
        """
        Main ingestion pipeline for processing a document.

        Args:
            request: Ingestion request containing file information

        Returns:
            Ingestion response with processing results
        """
        try:
            # Process request to extract knowledge_id, filename, and file_path
            processed_request = await self._process_ingestion_request(request)
            knowledge_id = processed_request["knowledge_id"]
            filename = processed_request["filename"]
            file_path = processed_request["file_path"]

            logger.info(
                f"Starting ingestion: knowledge_id={knowledge_id}, "
                f"filename={filename}, file_path={file_path}"
            )

            # Step 1: Load document
            documents = await self._load_document(file_path)
            if not documents:
                raise VectorStoreError("No documents were loaded from the file")

            # Step 2: Split documents into chunks
            chunks = await self._split_documents(documents)
            if not chunks:
                raise VectorStoreError("No chunks were created from the documents")

            # Step 3: Generate unique IDs for chunks
            document_ids = self.generate_document_ids(len(chunks))

            # Step 4: Add IDs to chunk metadata
            for chunk, doc_id in zip(chunks, document_ids):
                chunk.metadata["document_id"] = doc_id
                chunk.metadata["knowledge_id"] = knowledge_id

            # Step 5: Get vector store and embedding model
            vector_store = await self.vector_store.get_vector_store(knowledge_id)

            # Step 6: Add documents to vector store
            await self._add_documents_to_vector_store(
                vector_store, chunks, document_ids
            )

            # Step 7: Record file metadata
            await self.record_manager.add_file_records(
                filename, document_ids, knowledge_id
            )

            logger.info(
                f"Successfully ingested document: knowledge_id={knowledge_id}, "
                f"filename={filename}, chunks={len(chunks)}"
            )

            return IngestionResponse(
                success=True,
                message="Document ingested successfully",
                knowledge_id=knowledge_id,
                filename=filename,
                document_count=len(chunks),
                document_ids=document_ids,
            )

        except Exception as e:
            error_msg = f"Ingestion failed: {str(e)}"
            logger.error(error_msg)

            # Try to get knowledge_id and filename for error response
            try:
                processed_request = await self._process_ingestion_request(request)
                knowledge_id = processed_request["knowledge_id"]
                filename = processed_request["filename"]
            except:
                knowledge_id = request.knowledge_id or "unknown"
                filename = request.filename or "unknown"

            return IngestionResponse(
                success=False,
                message=error_msg,
                knowledge_id=knowledge_id,
                filename=filename,
                document_count=0,
                document_ids=[],
            )

    async def remove_document(
        self, knowledge_id: str, filename: str
    ) -> DocumentRemovalResponse:
        """
        Remove a document from the knowledge base.

        Args:
            knowledge_id: Knowledge base identifier
            filename: Name of the file to remove

        Returns:
            Document removal response
        """
        logger.info(
            f"Removing document: knowledge_id={knowledge_id}, filename={filename}"
        )

        try:
            # Get document IDs for the file
            document_ids = await self.record_manager.remove_file_records(
                filename, knowledge_id
            )

            if not document_ids:
                return DocumentRemovalResponse(
                    success=False,
                    message="No documents found for the specified file",
                    knowledge_id=knowledge_id,
                    filename=filename,
                    removed_count=0,
                )

            # Remove documents from vector store
            vector_store = await self.vector_store.get_vector_store(knowledge_id)
            await vector_store.adelete(ids=document_ids)

            logger.info(
                f"Successfully removed document: knowledge_id={knowledge_id}, "
                f"filename={filename}, removed_count={len(document_ids)}"
            )

            return DocumentRemovalResponse(
                success=True,
                message="Document removed successfully",
                knowledge_id=knowledge_id,
                filename=filename,
                removed_count=len(document_ids),
            )

        except Exception as e:
            error_msg = f"Document removal failed: {str(e)}"
            logger.error(error_msg)

            return DocumentRemovalResponse(
                success=False,
                message=error_msg,
                knowledge_id=knowledge_id,
                filename=filename,
                removed_count=0,
            )

    async def get_ingestion_status(self, knowledge_id: str) -> IngestionStatusResponse:
        """
        Get status of ingestion for a knowledge base.

        Args:
            knowledge_id: Knowledge base identifier

        Returns:
            Ingestion status response
        """
        logger.debug(f"Getting ingestion status for knowledge_id: {knowledge_id}")

        try:
            stats = await self.record_manager.get_knowledge_base_stats(knowledge_id)

            return IngestionStatusResponse(
                knowledge_id=knowledge_id,
                total_files=stats["total_files"],
                total_documents=stats["total_documents"],
                files=stats["files"],
            )

        except Exception as e:
            logger.error(f"Failed to get ingestion status: {str(e)}")
            return IngestionStatusResponse(
                knowledge_id=knowledge_id,
                total_files=0,
                total_documents=0,
                files=[],
            )

    async def _process_ingestion_request(self, request: IngestionRequest) -> dict:
        """
        Process ingestion request to construct S3 URL and prepare for ingestion.

        Args:
            request: Ingestion request with knowledge_id and filename

        Returns:
            Dict with knowledge_id, filename, and constructed S3 URL (file_path)
        """
        # Construct S3 URL from configuration and request parameters
        s3_url = s3_service.construct_s3_url(request.knowledge_id, request.filename)

        return {
            "knowledge_id": request.knowledge_id,
            "filename": request.filename,
            "file_path": s3_url,
        }

    async def _load_document(self, s3_url: str) -> List[Document]:
        """Load document from S3 URL."""
        logger.debug(f"Loading document: {s3_url}")
        return await self.document_loader.load_document(s3_url)

    async def _split_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks."""
        logger.debug(f"Splitting {len(documents)} documents")
        return await self.text_splitter.split_documents(documents)

    async def _add_documents_to_vector_store(
        self,
        vector_store,
        chunks: List[Document],
        document_ids: List[str],
    ) -> None:
        """Add document chunks to vector store."""
        logger.debug(f"Adding {len(chunks)} chunks to vector store")

        # Extract text content for embedding
        texts = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        # # log one the text and metadata
        # logger.debug(f"text: {texts[0]}")
        # logger.debug(f"metadata: {metadatas[0]}")

        # Add to vector store with specific IDs
        await vector_store.aadd_texts(
            texts=texts,
            metadatas=metadatas,
            ids=document_ids,
        )


# Singleton instance
ingestion_service = IngestionService()
