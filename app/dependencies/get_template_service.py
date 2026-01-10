from functools import lru_cache
from app.services.llm import LLMService
from app.services.template import TemplateService


@lru_cache(maxsize=1)
def get_template_service() -> TemplateService:
    """
    Dependency provider for TemplateService.
    Returns a cached singleton instance since the service is stateless.
    
    Returns:
        TemplateService: Initialized service instance
    """
    # Create a new LLM service instance for the template service
    llm_service = LLMService()
    return TemplateService(llm_service=llm_service)
