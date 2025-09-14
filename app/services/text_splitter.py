"""Text splitting service for document chunking."""

from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class TextSplitterService:
    """Service for splitting documents into chunks."""

    def __init__(self) -> None:
        """Initialize text splitter."""
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            is_separator_regex=False,
        )

    async def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into smaller chunks for embedding.

        Args:
            documents: List of documents to split

        Returns:
            List of document chunks
        """
        if not documents:
            return []

        logger.info(f"Splitting {len(documents)} documents into chunks")

        # Split all documents
        chunks = []
        for doc in documents:
            doc_chunks = self.text_splitter.split_documents([doc])
            chunks.extend(doc_chunks)

        logger.info(f"Split into {len(chunks)} chunks")

        return chunks


# Singleton instance
text_splitter_service = TextSplitterService()
