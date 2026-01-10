from typing import List, Optional
from pydantic import BaseModel, Field


class Score(BaseModel):
    name: str
    value: str


class Category(BaseModel):
    id: Optional[str] = None
    name: str
    scores: Optional[List[Score]] = Field(default=None)



class Option(BaseModel):
    title: str
    description: Optional[str] = ""


class NumericScale(BaseModel):
    min: int
    max: int
    step: int
    label1: str
    label2: str
    label3: str


class Question(BaseModel):
    title: str
    description: Optional[str] = Field(default=None)
    type: str
    options: Optional[List[Option]] = None
    selected_options: Optional[List[Option]] = Field(default=None, alias="selectedOptions")
    patient_text_response: Optional[str] = Field(default=None, alias="patientTextResponse")
    numeric_scale: Optional[NumericScale] = Field(default=None, alias="numericScale")
    selected_value: Optional[int] = Field(default=None, alias="selectedValue")

    class Config:
        populate_by_name = True


class ResponseItem(BaseModel):
    question: Question


class ReportItem(BaseModel):
    questionnaire_title: str = Field(alias="questionnaireTitle")
    report_id: Optional[str] = Field(default=None, alias="reportId")
    category: Category
    patient_response: List[ResponseItem] = Field(default_factory=list, alias="patientResponse")
    hcp_response: List[ResponseItem] = Field(default_factory=list, alias="hcpResponse")
    hcp_notes: Optional[str] = Field(default="", alias="hcpNotes")
    completed_at: Optional[str] = Field(default=None, alias="completedAt")

    class Config:
        populate_by_name = True


class LetterGenerationRequest(BaseModel):
    """Request model for letter generation."""
    report: List[ReportItem]
    instructions: str = Field(..., min_length=1, description="Instructions for generating the letter")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "report": [
                    {
                        "questionnaireTitle": "FINAL QUESTIONNAIRE!!!!",
                        "reportId": "251484dc-adb6-4eae-8db9-16410ff8bbf0",
                        "category": {
                            "id": "f79a53c6-af5b-4cab-ae04-550aa34e00b7",
                            "name": "One",
                            "scores": [
                                {"name": "Score 1", "value": "20"},
                                {"name": "Score 2", "value": "20"},
                                {"name": "Score 3", "value": "1000"},
                                {"name": "Total Category 1 Sum", "value": "10"}
                            ]
                        },
                        "patientResponse": [
                            {
                                "question": {
                                    "title": "q2",
                                    "description": "",
                                    "type": "MultiSelectText",
                                    "options": [{"title": "Option 1", "description": ""}, {"title": "Option 2", "description": ""}],
                                    "selectedOptions": [{"title": "Option 1", "description": ""}]
                                }
                            }
                        ],
                        "hcpResponse": [],
                        "hcpNotes": "this is doctore note",
                        "completedAt": "2025-09-19T10:53:15+03:30"
                    }
                ],
                "instructions": "Write a referral letter based on this report."
            }
        }
