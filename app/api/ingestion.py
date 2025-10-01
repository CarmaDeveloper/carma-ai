"""Ingestion API endpoints for document processing."""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse

from app.core.exceptions import VectorStoreError
from app.core.logging import setup_logger
from app.models.ingestion import (
    IngestionRequest,
    IngestionResponse,
    IngestionStatusResponse,
    DocumentRemovalRequest,
    DocumentRemovalResponse,
)
from app.services.ingestion import ingestion_service

logger = setup_logger(__name__)

router = APIRouter(tags=["ingestion"], prefix="/v1/ingestion")


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a document from S3 into a knowledge base",
    description="""
    Ingest a document from AWS S3 into a knowledge base by processing it through the following pipeline:
    
    1. **Download Document**: Download the document from S3 using the constructed URL
    2. **Load Document**: Load the downloaded document using appropriate loader
    3. **Split Text**: Split the document into chunks for optimal vector storage
    4. **Generate Embeddings**: Create vector embeddings for each chunk
    5. **Store Vectors**: Store embeddings in the vector database
    6. **Record Metadata**: Track document chunks and their relationships
    
    **S3 URL Construction:**
    Documents are automatically located using: `s3://{bucket}/knowledge/{knowledge_id}/{filename}`
    
    **Supported File Types:**
    - PDF (.pdf)
    - Text (.txt)
    - Word Documents (.docx, .doc)
    - CSV (.csv)
    - Markdown (.md, .markdown)
    - HTML (.html, .htm)
    
    **Parameters:**
    - `knowledge_id`: Unique identifier for the knowledge base (used in S3 path)
    - `filename`: Name of the file to process from S3
    """,
)
async def ingest_document(request: IngestionRequest) -> IngestionResponse:
    """
    Ingest a single document from S3 into a knowledge base.

    Args:
        request: Ingestion request containing knowledge_id and filename

    Returns:
        Ingestion response with processing results

    Raises:
        HTTPException: If ingestion fails, file not found in S3, or file type not supported
    """
    try:
        logger.info(
            f"API: Ingesting S3 document - knowledge_id: {request.knowledge_id}, "
            f"filename: {request.filename}"
        )

        response = await ingestion_service.ingest_document(request)

        if not response.success:
            logger.warning(f"S3 ingestion failed: {response.message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="S3 ingestion failed",
            )

        logger.info(
            f"API: S3 document ingested successfully - "
            f"knowledge_id: {request.knowledge_id}, chunks: {response.document_count}"
        )

        return response

    except HTTPException:
        raise
    except VectorStoreError as e:
        logger.error(f"Vector store error during S3 ingestion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vector store error during S3 ingestion",
        )
    except Exception as e:
        logger.error(f"Unexpected error during S3 ingestion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document ingestion",
        )


@router.post(
    "/ingest-async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a document from S3 asynchronously",
    description="""
    Start S3 document ingestion as a background task. This endpoint returns immediately
    while the ingestion process continues in the background.
    
    The document will be downloaded from S3 and processed asynchronously.
    Use the status endpoint to check the progress of the ingestion.
    """,
)
async def ingest_document_async(
    request: IngestionRequest, background_tasks: BackgroundTasks
) -> JSONResponse:
    """
    Start S3 document ingestion as a background task.

    Args:
        request: Ingestion request containing knowledge_id and filename
        background_tasks: FastAPI background tasks handler

    Returns:
        Acceptance response with task information
    """
    try:
        logger.info(
            f"API: Starting async S3 ingestion - knowledge_id: {request.knowledge_id}, "
            f"filename: {request.filename}"
        )

        # Add ingestion task to background tasks
        background_tasks.add_task(_background_ingest_task, request)

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "S3 document ingestion started",
                "knowledge_id": request.knowledge_id,
                "filename": request.filename,
                "status": "processing",
            },
        )

    except Exception as e:
        logger.error(f"Failed to start async S3 ingestion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start background ingestion task",
        )


@router.delete(
    "/remove",
    response_model=DocumentRemovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove a document from a knowledge base",
    description="""
    Remove a document and all its associated chunks from a knowledge base.
    
    This operation:
    1. Removes all document chunks from the vector store
    2. Removes metadata records from the record manager
    3. Returns the count of removed chunks
    """,
)
async def remove_document(request: DocumentRemovalRequest) -> DocumentRemovalResponse:
    """
    Remove a document from a knowledge base.

    Args:
        request: Document removal request

    Returns:
        Document removal response with results

    Raises:
        HTTPException: If removal fails
    """
    try:
        logger.info(
            f"API: Removing document - knowledge_id: {request.knowledge_id}, "
            f"filename: {request.filename}"
        )

        response = await ingestion_service.remove_document(
            request.knowledge_id, request.filename
        )

        if not response.success:
            logger.warning(f"Document removal failed: {response.message}")
            if "not found" in response.message.lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Document removal failed",
                )

        logger.info(
            f"API: Document removed successfully - "
            f"knowledge_id: {request.knowledge_id}, removed: {response.removed_count}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during document removal: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document removal",
        )


@router.get(
    "/status/{knowledge_id}",
    response_model=IngestionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ingestion status for a knowledge base",
    description="""
    Get the current status of document ingestion for a specific knowledge base.
    
    Returns information about:
    - Total number of files ingested
    - Total number of document chunks
    - List of all filenames in the knowledge base
    """,
)
async def get_ingestion_status(knowledge_id: str) -> IngestionStatusResponse:
    """
    Get ingestion status for a knowledge base.

    Args:
        knowledge_id: Knowledge base identifier

    Returns:
        Ingestion status response

    Raises:
        HTTPException: If status retrieval fails
    """
    try:
        logger.debug(f"API: Getting ingestion status for knowledge_id: {knowledge_id}")

        response = await ingestion_service.get_ingestion_status(knowledge_id)

        logger.debug(
            f"API: Status retrieved - knowledge_id: {knowledge_id}, "
            f"files: {response.total_files}, documents: {response.total_documents}"
        )

        return response

    except Exception as e:
        logger.error(f"Failed to get ingestion status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ingestion status",
        )


@router.get(
    "/supported-formats",
    status_code=status.HTTP_200_OK,
    summary="Get supported file formats",
    description="Get a list of file formats supported for document ingestion.",
)
async def get_supported_formats() -> JSONResponse:
    """
    Get list of supported file formats for ingestion.

    Returns:
        List of supported file extensions and their descriptions
    """
    try:
        from app.services.document_loader import document_loader_service

        extensions = document_loader_service.get_supported_extensions()

        format_descriptions = {
            ".pdf": "Portable Document Format",
            ".txt": "Plain Text",
            ".docx": "Microsoft Word Document (Office Open XML)",
            ".doc": "Microsoft Word Document (Legacy)",
            ".csv": "Comma-Separated Values",
            ".md": "Markdown",
            ".markdown": "Markdown",
            ".html": "HyperText Markup Language",
            ".htm": "HyperText Markup Language",
        }

        supported_formats = [
            {
                "extension": ext,
                "description": format_descriptions.get(ext, "Supported format"),
                "supported": True,
            }
            for ext in extensions
        ]

        return JSONResponse(
            content={
                "supported_formats": supported_formats,
                "total_formats": len(supported_formats),
            }
        )

    except Exception as e:
        logger.error(f"Failed to get supported formats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve supported formats",
        )


async def _background_ingest_task(request: IngestionRequest) -> None:
    """
    Background task for S3 document ingestion.

    Args:
        request: Ingestion request to process
    """
    try:
        logger.info(f"Background: Starting S3 ingestion for {request.filename}")

        response = await ingestion_service.ingest_document(request)

        if response.success:
            logger.info(
                f"Background: S3 ingestion completed successfully - "
                f"chunks: {response.document_count}"
            )
        else:
            logger.error(f"Background: S3 ingestion failed - {response.message}")

    except Exception as e:
        logger.error(f"Background: S3 ingestion task failed - {str(e)}")
