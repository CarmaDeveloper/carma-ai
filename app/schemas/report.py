"""Report generation models."""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class QAItem(BaseModel):
    """Question and answer pair with optional hierarchical sub-questions."""

    question: str = Field(..., description="The question")
    answer: str = Field(..., description="The answer")
    sub_questions: Optional[List["QAItem"]] = Field(
        None, description="Optional list of sub-questions related to this question"
    )


# Update forward references for recursive model
QAItem.model_rebuild()


class ReportGenerationRequest(BaseModel):
    """Request model for report generation."""

    knowledge_id: Optional[str] = Field(
        None, description="Optional knowledge base ID for context retrieval"
    )
    prompt: str = Field(..., description="Prompt for report generation")
    qas: List[QAItem] = Field(
        default_factory=list, description="Optional list of question-answer pairs"
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

    # Accept both legacy_score and scores; no mutual exclusion validator

    def get_scores(self) -> Optional[Dict[str, float]]:
        """Get merged scores; categorized scores take precedence, legacy fills overall."""
        merged: Dict[str, float] = {}
        # Incorporate categorized scores first (highest precedence)
        if self.scores:
            merged.update({k: float(v) for k, v in self.scores.items()})
        # Incorporate legacy score as overall if present and not already provided
        if self.legacy_score is not None:
            if isinstance(self.legacy_score, dict):
                for k, v in self.legacy_score.items():
                    if k not in merged:
                        merged[k] = float(v)
            else:
                if "overall" not in merged:
                    merged["overall"] = float(self.legacy_score)
        return merged or None

    class Config:
        json_schema_extra = {
            "example": {
                "knowledge_id": "kb-123",
                "prompt": "Analyze the healthcare Q&A data to identify key treatment recommendations and patterns. Focus on evidence-based interventions and create a summary report with actionable insights for healthcare professionals.",
                "qas": [
                    {
                        "question": "How is your overall health?",
                        "answer": "Good",
                        "sub_questions": [
                            {
                                "question": "Do you have any chronic conditions?",
                                "answer": "Yes, diabetes",
                                "sub_questions": [
                                    {
                                        "question": "How long have you had diabetes?",
                                        "answer": "5 years",
                                    }
                                ],
                            },
                            {
                                "question": "Are you taking any medications?",
                                "answer": "Yes, metformin",
                                "sub_questions": [
                                    {
                                        "question": "Dosage?",
                                        "answer": "500mg",
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "question": "What is your primary concern today?",
                        "answer": "Blood sugar management",
                    },
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


# Models for Insight Generation

class OptionDetail(BaseModel):
    title: str = Field(..., alias="title")
    description: Optional[str] = Field(None, alias="description")


class NumericScaleDetail(BaseModel):
    min: int = Field(..., alias="min")
    max: int = Field(..., alias="max")
    step: int = Field(..., alias="step")
    label1: str = Field(..., alias="label1")
    label2: str = Field(..., alias="label2")
    label3: str = Field(..., alias="label3")


class QuestionDetail(BaseModel):
    """Question detail with response."""
    title: str = Field(..., alias="title")
    description: Optional[str] = Field(None, alias="description")
    type: str = Field(..., alias="type")
    options: Optional[List[OptionDetail]] = Field(None, alias="options")
    selected_options: Optional[List[OptionDetail]] = Field(None, alias="selectedOptions")
    patient_text_response: Optional[str] = Field(None, alias="patientTextResponse")
    numeric_scale: Optional[NumericScaleDetail] = Field(None, alias="numericScale")
    selected_value: Optional[int] = Field(None, alias="selectedValue")


class QuestionResponseDetail(BaseModel):
    question: QuestionDetail = Field(..., alias="question")


class CategoryScoreDetail(BaseModel):
    name: str = Field(..., alias="name")
    value: str = Field(..., alias="value")


class CategoryDetail(BaseModel):
    id: str = Field(..., alias="id")
    name: str = Field(..., alias="name")
    scores: Optional[List[CategoryScoreDetail]] = Field(None, alias="scores")



class ReportItemDetail(BaseModel):
    questionnaire_title: str = Field(..., alias="questionnaireTitle")
    report_id: str = Field(..., alias="reportId")
    category: CategoryDetail = Field(..., alias="category")
    patient_response: Optional[List[QuestionResponseDetail]] = Field(None, alias="patientResponse")
    hcp_response: Optional[List[QuestionResponseDetail]] = Field(None, alias="hcpResponse")
    completed_at: str = Field(..., alias="completedAt")


class InsightGenerationRequest(BaseModel):
    """Request model for insight generation."""
    report: List[ReportItemDetail] = Field(..., description="List of report items")
    knowledge_id: Optional[str] = Field(None, alias="knowledgeId", description="Optional knowledge base ID for context retrieval")
    prompt: Optional[str] = Field(None, description="Optional prompt for insight generation")


class ReferenceItem(BaseModel):
    """Reference item with title and S3 download URL."""
    title: str = Field(..., description="User-defined display title for the document")
    url: str = Field(..., description="S3 HTTPS URL to download the file")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Annual Health Report 2024",
                "url": "https://bucket.s3.region.amazonaws.com/knowledge/uuid/report.pdf"
            }
        }
