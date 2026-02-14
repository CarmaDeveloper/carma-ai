"""Ingestion models for document processing."""

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class SubReference(BaseModel):
    """A sub-reference associated with a document, containing a title and a link."""

    title: str = Field(..., description="Display title of the sub-reference")
    link: str = Field(..., description="URL link of the sub-reference")


class IngestionRequest(BaseModel):
    """Request model for document ingestion."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "knowledge_id": "a71860c9-b8df-47c5-a11f-3e1ac6086026",
                "filename": "test.pdf",
                "title": "Technical Specification Document",
                "sub_references": [
                    {"title": "Appendix A", "link": "https://example.com/appendix-a"}
                ],
            }
        }
    )

    knowledge_id: str = Field(..., description="Knowledge base identifier (UUID)")
    filename: str = Field(..., description="Name of the file in S3 bucket (e.g., 'report_2024.pdf')")
    title: str = Field(..., description="User-defined display title for the document (e.g., 'Annual Report 2024')")
    sub_references: Optional[List[SubReference]] = Field(
        default=None,
        description="Optional list of sub-references (title and link) associated with this document",
    )


class IngestionResponse(BaseModel):
    """Response model for document ingestion."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Document ingested successfully",
                "knowledge_id": "project_docs",
                "filename": "technical_specification.pdf",
                "title": "Technical Specification Document",
                "sub_references": [
                    {"title": "Appendix A", "link": "https://example.com/appendix-a"}
                ],
                "document_count": 15,
                "document_ids": ["uuid1", "uuid2", "uuid3"],
            }
        }
    )

    success: bool = Field(..., description="Whether ingestion was successful")
    message: str = Field(..., description="Status message")
    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Name of the file in S3 bucket")
    title: str = Field(..., description="User-defined display title for the document")
    sub_references: List[SubReference] = Field(
        default_factory=list,
        description="List of sub-references associated with this document",
    )
    document_count: int = Field(..., description="Number of document chunks created")
    document_ids: List[str] = Field(..., description="List of generated document IDs")


class IngestionStatusRequest(BaseModel):
    """Request model for checking ingestion status."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: Optional[str] = Field(default=None, description="Optional S3 filename filter")


class IngestionStatusResponse(BaseModel):
    """Response model for ingestion status."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    total_files: int = Field(..., description="Total number of files in knowledge base")
    total_documents: int = Field(..., description="Total number of document chunks")
    files: List[str] = Field(..., description="List of filenames in knowledge base")


class DocumentRemovalRequest(BaseModel):
    """Request model for removing documents."""

    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Name of the file in S3 bucket to remove")


class DocumentRemovalResponse(BaseModel):
    """Response model for document removal."""

    success: bool = Field(..., description="Whether removal was successful")
    message: str = Field(..., description="Status message")
    knowledge_id: str = Field(..., description="Knowledge base identifier")
    filename: str = Field(..., description="Name of the removed file from S3 bucket")
    removed_count: int = Field(..., description="Number of document chunks removed")


