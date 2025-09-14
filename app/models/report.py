"""Report generation models."""

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, validator


class QAItem(BaseModel):
    """Question and answer pair."""

    question: str = Field(..., description="The question")
    answer: str = Field(..., description="The answer")


PromptMessage = Tuple[Literal["system", "human"], str]


class ReportGenerationRequest(BaseModel):
    """Request model for report generation."""

    knowledge_id: Optional[str] = Field(
        None, description="Optional knowledge base ID for context retrieval"
    )
    prompt: List[PromptMessage] = Field(
        ..., description="List of prompt messages with role and content"
    )
    qas: List[QAItem] = Field(
        ..., description="List of question-answer pairs", min_items=1
    )

    @validator("prompt")
    def validate_prompt(cls, v):
        """Validate prompt messages."""
        if not v:
            raise ValueError("Prompt cannot be empty")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "knowledge_id": "kb-123",
                "prompt": [
                    ["system", "You are a helpful assistant that generates reports."],
                    [
                        "human",
                        "Generate a report based on the provided context and Q&A pairs.",
                    ],
                ],
                "qas": [
                    {
                        "question": "What is the main topic?",
                        "answer": "The main topic is artificial intelligence.",
                    }
                ],
            }
        }


class TokenUsage(BaseModel):
    """Token usage information."""
    
    input_tokens: int = Field(..., description="Number of input tokens used")
    output_tokens: int = Field(..., description="Number of output tokens generated")
    total_tokens: int = Field(..., description="Total number of tokens used")


class ReportGenerationResponse(BaseModel):
    """Response model for report generation."""

    message: str = Field(..., description="Generated report content")
    references: List[str] = Field(
        default_factory=list, description="List of reference file names"
    )
    document_ids: List[str] = Field(
        default_factory=list, description="List of document IDs used for generation"
    )
    knowledge_id: Optional[str] = Field(
        None, description="Knowledge base ID used for generation"
    )
    token_usage: Optional[TokenUsage] = Field(
        None, description="Token usage information for the generation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Based on the provided information, here is the generated report...",
                "references": ["document1.pdf", "report2.docx"],
                "document_ids": ["doc-123", "doc-456"],
                "knowledge_id": "kb-123",
                "token_usage": {
                    "input_tokens": 1250,
                    "output_tokens": 350,
                    "total_tokens": 1600
                }
            }
        }
