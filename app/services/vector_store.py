"""Vector store service for similarity search."""

from typing import List

from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

from app.core.config import settings
from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger
from app.services.embedding import embedding_service

logger = setup_logger(__name__)


class VectorStoreService:
    """Service for vector store operations."""

    def __init__(self) -> None:
        """Initialize vector store service."""
        self.provider = settings.VECTOR_STORE_PROVIDER
        self._stores = {}  # Cache for different knowledge bases

    async def get_vector_store(self, knowledge_id: str):
        """Get vector store instance for a knowledge base."""
        if knowledge_id not in self._stores:
            self._stores[knowledge_id] = self._create_vector_store(knowledge_id)
        return self._stores[knowledge_id]

    def _create_vector_store(self, knowledge_id: str):
        """Create vector store based on provider."""
        if self.provider == "pg-vector":
            return self._create_pgvector_store(knowledge_id)
        else:
            raise VectorStoreError(
                f"Unsupported vector store provider: {self.provider}"
            )

    def _create_pgvector_store(self, knowledge_id: str):
        """Create PostgreSQL vector store instance."""
        try:
            logger.info(
                f"Initializing PGVector store: knowledge_id={knowledge_id}, "
                f"database_host={settings.POSTGRES_HOST}, "
                f"database_port={settings.POSTGRES_PORT}, "
                f"database_name={settings.POSTGRES_DB}"
            )

            embedding_model = embedding_service.get_embedding_model()

            # Create collection name based on knowledge_id
            collection_name = f"knowledge_{knowledge_id}"

            return PGVector(
                connection_string=settings.DATABASE_URL,
                embedding_function=embedding_model,
                collection_name=collection_name,
                use_jsonb=True,
            )

        except Exception as e:
            logger.error(
                f"Failed to create PGVector store: knowledge_id={knowledge_id}, error={str(e)}"
            )
            raise VectorStoreError(f"Failed to initialize vector store: {str(e)}")

    async def similarity_search(
        self, knowledge_id: str, queries: List[str], k: int = 4
    ) -> List[Document]:
        """
        Perform similarity search across multiple queries.

        Args:
            knowledge_id: Knowledge base identifier
            queries: List of query strings
            k: Number of documents to retrieve per query

        Returns:
            List of relevant documents

        Raises:
            VectorStoreError: If search fails
        """
        if not queries:
            return []

        try:
            logger.info(
                f"Performing similarity search: knowledge_id={knowledge_id}, "
                f"query_count={len(queries)}, k={k}"
            )

            vector_store = await self.get_vector_store(knowledge_id)
            retriever = vector_store.as_retriever(search_kwargs={"k": k})

            # Perform searches for all queries
            all_docs = []
            for query in queries:
                docs = await retriever.ainvoke(query)
                all_docs.extend(docs)

            # Remove duplicates based on document content
            unique_docs = []
            seen_content = set()
            logger.info(f"All docs: {all_docs}")
            for doc in all_docs:
                content_hash = hash(doc.page_content)
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    unique_docs.append(doc)

            # Log details about retrieved documents
            self._log_retrieved_documents(knowledge_id, unique_docs)

            logger.info(
                f"Completed similarity search: knowledge_id={knowledge_id}, "
                f"total_docs={len(all_docs)}, unique_docs={len(unique_docs)}"
            )

            return unique_docs

        except Exception as e:
            logger.error(
                f"Similarity search failed: knowledge_id={knowledge_id}, error={str(e)}"
            )
            raise VectorStoreError(f"Vector search failed: {str(e)}")

    def _log_retrieved_documents(
        self, knowledge_id: str, documents: List[Document]
    ) -> None:
        """Log detailed information about retrieved documents."""
        logger.info(f"=== RETRIEVED DOCUMENTS FROM VECTOR STORE ===")
        logger.info(f"Knowledge ID: {knowledge_id}")
        logger.info(f"Total documents retrieved: {len(documents)}")

        for i, doc in enumerate(documents, 1):
            # Extract key metadata
            source_file = doc.metadata.get("source_file", "Unknown")
            document_id = doc.metadata.get("document_id", "Unknown")
            file_name = doc.metadata.get("file_name", "Unknown")
            source_s3_url = doc.metadata.get("source_s3_url", "Unknown")

            # Log document details
            logger.info(f"Document {i}:")
            logger.info(f"  - Document ID: {document_id}")
            logger.info(f"  - Source File: {source_file}")
            logger.info(f"  - File Name: {file_name}")
            logger.info(f"  - S3 URL: {source_s3_url}")
            logger.info(f"  - Content preview: {doc.page_content[:200]}...")
            logger.info(f"  - Full metadata: {doc.metadata}")

        logger.info(f"=== END RETRIEVED DOCUMENTS ===")


# Singleton instance
vector_store_service = VectorStoreService()
