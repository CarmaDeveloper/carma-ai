from functools import lru_cache
from app.services.llm import LLMService
from app.services.letter import LetterService


@lru_cache(maxsize=1)
def get_letter_service() -> LetterService:
    """
    Dependency provider for LetterService.
    Returns a cached singleton instance since the service is stateless.
    
    Returns:
        LetterService: Initialized service instance
    """
    # Create a new LLM service instance for the letter service
    llm_service = LLMService()
    return LetterService(llm_service=llm_service)

