"""Report generation models."""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class QAItem(BaseModel):
    """Question and answer pair."""

    question: str = Field(..., description="The question")
    answer: str = Field(..., description="The answer")


class ReportGenerationRequest(BaseModel):
    """Request model for report generation."""

    knowledge_id: Optional[str] = Field(
        None, description="Optional knowledge base ID for context retrieval"
    )
    prompt: str = Field(..., description="Prompt for report generation")
    qas: List[QAItem] = Field(
        ..., description="List of question-answer pairs", min_items=1
    )
    legacy_score: Optional[Union[float, Dict[str, Union[str, float]]]] = Field(
        None,
        description="Either a single legacy score (float) or categorized legacy scores (Dict[str, Union[str, float]]). Cannot be provided if scores is also provided.",
    )
    scores: Optional[Dict[str, Union[str, float]]] = Field(
        None,
        description="Categorized scores as a dictionary with category names as keys and scores as values. Cannot be provided if legacy_score is also provided.",
    )

    @validator("prompt")
    def validate_prompt(cls, v):
        """Allow empty prompt; normalize whitespace."""
        if v is None:
            return ""
        return v.strip()

    @validator("scores")
    def validate_scores_not_both(cls, v, values):
        """Validate that both score and scores are not provided."""
        if v is not None and values.get("legacy_score") is not None:
            raise ValueError("Cannot provide both 'legacy_score' and 'scores' fields")
        return v

    def get_scores(self) -> Optional[Dict[str, float]]:
        """Get scores as a dictionary, handling both single score and categorized formats."""
        if self.scores is not None:
            # Convert string values to float
            return {k: float(v) for k, v in self.scores.items()}
        elif self.legacy_score is not None:
            if isinstance(self.legacy_score, dict):
                # Convert string values to float
                return {k: float(v) for k, v in self.legacy_score.items()}
            else:
                # Single overall score
                return {"overall": float(self.legacy_score)}
        return None

    class Config:
        json_schema_extra = {
            "example": {
                "knowledge_id": "kb-123",
                "prompt": "Analyze the healthcare Q&A data to identify key treatment recommendations and patterns. Focus on evidence-based interventions and create a summary report with actionable insights for healthcare professionals.",
                "qas": [
                    {
                        "question": "What is the main topic?",
                        "answer": "The main topic is artificial intelligence.",
                    }
                ],
                "legacy_score": 85.5,  # Single legacy score format
                # OR alternatively:
                # "scores": {"health": "100", "body": "10"}  # Categorized scores format
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
                    "total_tokens": 1600,
                },
            }
        }
