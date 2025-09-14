"""Document loader service for processing S3 documents."""

from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    PyPDFLoader,
    CSVLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredHTMLLoader,
)
from langchain_core.documents import Document

from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger
from app.services.s3 import s3_service

logger = setup_logger(__name__)


class DocumentLoaderService:
    """Service for loading documents from S3 buckets."""

    # Mapping of file extensions to their corresponding loaders
    SUPPORTED_EXTENSIONS = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".docx": Docx2txtLoader,
        ".doc": Docx2txtLoader,
        ".csv": CSVLoader,
        ".md": UnstructuredMarkdownLoader,
        ".markdown": UnstructuredMarkdownLoader,
        ".html": UnstructuredHTMLLoader,
        ".htm": UnstructuredHTMLLoader,
    }

    def __init__(self) -> None:
        """Initialize document loader service."""
        pass

    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.

        Returns:
            List of supported file extensions
        """
        return list(self.SUPPORTED_EXTENSIONS.keys())

    def is_supported_file(self, filename: str) -> bool:
        """
        Check if file type is supported based on filename.

        Args:
            filename: Name of the file

        Returns:
            True if file type is supported, False otherwise
        """
        extension = Path(filename).suffix.lower()
        return extension in self.SUPPORTED_EXTENSIONS

    async def load_document(self, s3_url: str) -> List[Document]:
        """
        Load a document from S3 URL.

        Args:
            s3_url: S3 URL of the document to load

        Returns:
            List of Document objects

        Raises:
            VectorStoreError: If file is not supported or loading fails
        """
        if not s3_service.is_s3_url(s3_url):
            raise VectorStoreError(
                f"Invalid S3 URL: {s3_url}. Only S3 URLs are supported."
            )

        return await self._load_document_from_s3(s3_url)

    async def _load_document_from_s3(self, s3_url: str) -> List[Document]:
        """
        Load a document from S3.

        Args:
            s3_url: S3 URL of the document

        Returns:
            List of Document objects
        """
        temp_file_path = None

        try:
            # Extract filename and validate extension
            filename = s3_service.extract_filename_from_s3_path(s3_url)
            extension = Path(filename).suffix.lower()

            if extension not in self.SUPPORTED_EXTENSIONS:
                supported = ", ".join(self.SUPPORTED_EXTENSIONS.keys())
                raise VectorStoreError(
                    f"Unsupported file type: {extension}. "
                    f"Supported types: {supported}"
                )

            # Check if file exists in S3
            if not await s3_service.file_exists(s3_url):
                raise VectorStoreError(f"File not found in S3: {s3_url}")

            # Download file from S3 to temporary location
            logger.info(f"Downloading document from S3: {s3_url}")
            temp_file_path = await s3_service.download_file(s3_url)

            # Get the appropriate loader class
            loader_class = self.SUPPORTED_EXTENSIONS[extension]

            logger.info(f"Loading document: {filename} (type: {extension})")

            # Create loader instance and load document
            if extension == ".csv":
                # CSV loader needs special handling for encoding
                loader = loader_class(str(temp_file_path), encoding="utf-8")
            else:
                loader = loader_class(str(temp_file_path))

            documents = loader.load()

            # Add metadata about the source file
            for doc in documents:
                doc.metadata.update(
                    {
                        "source_s3_url": s3_url,
                        "source_file": filename,
                        "file_name": filename,
                        "file_extension": extension,
                        "file_size": temp_file_path.stat().st_size,
                        "source_type": "s3",
                    }
                )

            logger.info(
                f"Successfully loaded {len(documents)} document(s) from S3: {s3_url}"
            )
            return documents

        except Exception as e:
            error_msg = f"Failed to load document from S3 {s3_url}: {str(e)}"
            logger.error(error_msg)
            raise VectorStoreError(error_msg)
        finally:
            # Clean up temporary file
            if temp_file_path:
                s3_service.cleanup_temp_file(temp_file_path)


# Singleton instance
document_loader_service = DocumentLoaderService()
