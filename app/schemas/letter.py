from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PatientInformation(BaseModel):
    """Patient info at top level: birthDay and fullName (omitempty)."""

    model_config = ConfigDict(populate_by_name=True)

    birth_day: Optional[str] = Field(default=None, alias="birthDay")
    full_name: Optional[str] = Field(default=None, alias="fullName")


class Score(BaseModel):
    name: str
    value: str


class Category(BaseModel):
    name: str
    scores: Optional[List[Score]] = Field(default=None)


class Option(BaseModel):
    title: str
    description: Optional[str] = None


class NumericScale(BaseModel):
    min: int
    max: int
    step: int
    label1: str
    label2: str
    label3: str


class Question(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: Optional[str] = Field(default=None)
    type: str
    options: Optional[List[Option]] = None
    selected_options: Optional[List[Option]] = Field(default=None, alias="selectedOptions")
    patient_text_response: Optional[str] = Field(default=None, alias="patientTextResponse")
    numeric_scale: Optional[NumericScale] = Field(default=None, alias="numericScale")
    selected_value: Optional[int] = Field(default=None, alias="selectedValue")


class ResponseItem(BaseModel):
    question: Question


class CommunityResource(BaseModel):
    """Community resource with title and url (no id per spec)."""

    title: str
    url: str


class ReportItem(BaseModel):
    """Single report item: one category with responses and notes."""

    model_config = ConfigDict(populate_by_name=True)

    category: Category
    patient_response: Optional[List[ResponseItem]] = Field(default=None, alias="patientResponse")
    hcp_response: Optional[List[ResponseItem]] = Field(default=None, alias="hcpResponse")
    hcp_notes: Optional[str] = Field(default=None, alias="hcpNotes")
    patient_note: Optional[str] = Field(default=None, alias="patientNote")
    community_resources: Optional[List[CommunityResource]] = Field(
        default=None, alias="communityResources"
    )


class LetterGenerationRequest(BaseModel):
    """
    Request body for POST /letters/stream.
    Top-level: questionnaireTitle, patientInformation, completedAt (once), report, instructions.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "questionnaireTitle": "Complete Health Assessment",
                "patientInformation": {
                    "birthDay": "2000-05-15",
                    "fullName": "John Doe"
                },
                "completedAt": "2026-01-28T08:56:19Z",
                "report": [
                    {
                        "category": {
                            "name": "Kidney",
                            "scores": [
                                {"name": "Score Name", "value": "57"}
                            ]
                        },
                        "patientResponse": [
                            {
                                "question": {
                                    "title": "Question text",
                                    "type": "MultiSelectText",
                                    "selectedOptions": [{"title": "Option 1", "description": None}]
                                }
                            }
                        ],
                        "hcpResponse": None,
                        "hcpNotes": "Doctor note here",
                        "patientNote": "Patient note",
                        "communityResources": [
                            {"title": "Resource Title", "url": "https://example.com"}
                        ]
                    }
                ],
                "instructions": "Write a summary letter for the patient."
            }
        }
    )

    questionnaire_title: Optional[str] = Field(default=None, alias="questionnaireTitle")
    patient_information: Optional[PatientInformation] = Field(
        default=None, alias="patientInformation"
    )
    completed_at: Optional[str] = Field(default=None, alias="completedAt")
    report: List[ReportItem] = Field(..., description="Array of report items by category")
    instructions: str = Field(
        ..., min_length=1, description="User instructions for generating the letter"
    )
