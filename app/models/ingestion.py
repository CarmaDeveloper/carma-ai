"""Ingestion models for document processing."""

from typing import List, Optional

from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    """Request model for document ingestion."""

    knowledge_id: str = Field(..., description="Knowledge base identifier (UUID)")
    filename: str = Field(..., description="Name of the file to process")

    class Config:
        json_schema_extra = {
            "example": {
                "knowledge_id": "a71860c9-b8df-47c5-a11f-3e1ac6086026",
                "filename": "test.pdf",
            }
        }


class IngestionResponse(BaseModel):
    """Response model for document ingestion."""

    success: bool = Field(..., description="Whether ingestion was successful")
    message: str = Field(..., description="Status message")
    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Processed filename")
    document_count: int = Field(..., description="Number of document chunks created")
    document_ids: List[str] = Field(..., description="List of generated document IDs")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Document ingested successfully",
                "knowledge_id": "project_docs",
                "filename": "technical_specification.pdf",
                "document_count": 15,
                "document_ids": ["uuid1", "uuid2", "uuid3"],
            }
        }


class IngestionStatusRequest(BaseModel):
    """Request model for checking ingestion status."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: Optional[str] = Field(None, description="Optional filename filter")


class IngestionStatusResponse(BaseModel):
    """Response model for ingestion status."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    total_files: int = Field(..., description="Total number of files in knowledge base")
    total_documents: int = Field(..., description="Total number of document chunks")
    files: List[str] = Field(..., description="List of filenames in knowledge base")


class DocumentRemovalRequest(BaseModel):
    """Request model for removing documents."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Name of the file to remove")


class DocumentRemovalResponse(BaseModel):
    """Response model for document removal."""

    success: bool = Field(..., description="Whether removal was successful")
    message: str = Field(..., description="Status message")
    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Removed filename")
    removed_count: int = Field(..., description="Number of document chunks removed")
