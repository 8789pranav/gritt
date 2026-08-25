"""
Application exception hierarchy and FastAPI error handlers.

Services and engines raise these domain-level exceptions instead of
``HTTPException``. That keeps the business layers free of any HTTP concepts;
the translation to status codes happens once, in :func:`register_exception_handlers`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for every expected application error."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": False,
            "error": self.error_code,
            "detail": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


# ---------------------------------------------------------------------------
# 400 / 404 / 409 - client errors
# ---------------------------------------------------------------------------
class ValidationError(AppError):
    """A request carried semantically invalid data."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "validation_error"


class InvalidGradeError(ValidationError):
    """The supplied grade is not supported by the requested assessment."""

    error_code = "invalid_grade"

    def __init__(self, grade: str, supported: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Invalid grade: {grade!r}",
            details={"grade": grade, "supported": supported or []},
        )


class NotFoundError(AppError):
    """A requested resource does not exist."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ChildNotFoundError(NotFoundError):
    error_code = "child_not_found"

    def __init__(self, child_id: str) -> None:
        super().__init__("Child not found", details={"child_id": child_id})


class ItemNotFoundError(NotFoundError):
    error_code = "item_not_found"

    def __init__(self, item_id: str) -> None:
        super().__init__(f"Item {item_id!r} not found", details={"item_id": item_id})


class ResultNotFoundError(NotFoundError):
    error_code = "result_not_found"

    def __init__(self, test: str, child_id: str, grade: Optional[str] = None) -> None:
        suffix = f" in grade {grade}" if grade else ""
        super().__init__(
            f"No {test} results found for child {child_id}{suffix}",
            details={"test": test, "child_id": child_id, "grade": grade},
        )


# ---------------------------------------------------------------------------
# 402 - payment errors
# ---------------------------------------------------------------------------
class PaymentRequiredError(AppError):
    """The child has not been paid for; assessments are locked."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    error_code = "payment_required"

    def __init__(self, child_id: str) -> None:
        super().__init__(
            "Payment required for this child",
            details={"child_id": child_id},
        )


# ---------------------------------------------------------------------------
# 401 / 403 - auth errors
# ---------------------------------------------------------------------------
class AuthenticationError(AppError):
    """The caller could not be authenticated."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"


class InvalidTokenError(AuthenticationError):
    error_code = "invalid_token"

    def __init__(self, reason: str = "Invalid or expired token") -> None:
        super().__init__(reason)


class AuthorizationError(AppError):
    """The caller is authenticated but lacks permission."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "permission_denied"


class AdminRequiredError(AuthorizationError):
    error_code = "admin_required"

    def __init__(self) -> None:
        super().__init__("Admin access required")


# ---------------------------------------------------------------------------
# 5xx - upstream / infrastructure failures
# ---------------------------------------------------------------------------
class ExternalServiceError(AppError):
    """An upstream dependency failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "external_service_error"

    def __init__(self, service: str, message: str) -> None:
        super().__init__(f"{service}: {message}", details={"service": service})


class AudioGenerationError(ExternalServiceError):
    error_code = "audio_generation_failed"

    def __init__(self, message: str = "Unable to generate audio") -> None:
        super().__init__("tts", message)


class TranscriptionError(ExternalServiceError):
    error_code = "transcription_failed"

    def __init__(self, message: str = "Unable to transcribe audio") -> None:
        super().__init__("transcription", message)


class AnalysisError(ExternalServiceError):
    error_code = "analysis_failed"

    def __init__(self, message: str = "Unable to analyse response") -> None:
        super().__init__("analysis", message)


class DataFileError(AppError):
    """A question bank or tag config could not be loaded."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "data_file_error"


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that render :class:`AppError` subclasses as JSON."""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.error_code, exc.message, exc_info=exc)
        else:
            logger.info("%s: %s", exc.error_code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "internal_error",
                "detail": "An unexpected error occurred.",
            },
        )
