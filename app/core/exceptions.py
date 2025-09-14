"""Custom exception classes."""

from typing import Any, Dict, Optional


class CarmaRAGException(Exception):
    """Base exception for CARMA RAG application."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(CarmaRAGException):
    """Validation error exception."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=422, details=details)


class NotFoundError(CarmaRAGException):
    """Resource not found exception."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=404, details=details)


class ComprehendError(CarmaRAGException):
    """AWS Comprehend service error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=500, details=details)


class VectorStoreError(CarmaRAGException):
    """Vector store operation error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=500, details=details)


class ModelError(CarmaRAGException):
    """LLM model error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=500, details=details)
