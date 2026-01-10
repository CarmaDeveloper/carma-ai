from pydantic import BaseModel, Field

class TemplateGenerationRequest(BaseModel):
    """Request model for template generation."""
    
    prompt: str = Field(..., description="The user prompt to generate a template from", min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "Create a weekly status report template for a software engineering team."
            }
        }
