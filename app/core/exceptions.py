"""Custom exceptions and FastAPI exception handlers.

Implements RFC 7807 Problem Details for machine-readable error responses.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from app.core.logging import get_logger
from app.core.problem_details import (
    ERROR_TYPES,
    ProblemDetailResponse,
    problem_response,
)

logger = get_logger(__name__)


# =============================================================================
# Exception Classes
# =============================================================================


class ForecastLabError(Exception):
    """Base exception for ForecastLabAI application errors.

    All application-specific exceptions should inherit from this class.
    Each exception type maps to an RFC 7807 problem type URI.
    """

    # Default error type URI (override in subclasses)
    error_type_uri: str = ERROR_TYPES["INTERNAL_ERROR"]

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize application error.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            status_code: HTTP status code.
            details: Additional error context.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    @property
    def title(self) -> str:
        """RFC 7807 title - short summary of problem type."""
        return self.code.replace("_", " ").title()


class NotFoundError(ForecastLabError):
    """Resource not found error.

    Use when a requested resource (store, product, run, etc.) does not exist.
    Agents should check the resource ID and retry with a valid one.
    """

    error_type_uri: str = ERROR_TYPES["NOT_FOUND"]

    def __init__(
        self,
        message: str = "Resource not found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class ValidationError(ForecastLabError):
    """Input validation error.

    Use when request data fails validation.
    Agents should check the 'errors' field for specific field issues.
    """

    error_type_uri: str = ERROR_TYPES["VALIDATION_ERROR"]

    def __init__(
        self,
        message: str = "Validation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class DatabaseError(ForecastLabError):
    """Database operation error.

    Use when a database operation fails unexpectedly.
    Agents should retry after a delay or report for human investigation.
    """

    error_type_uri: str = ERROR_TYPES["DATABASE_ERROR"]

    def __init__(
        self,
        message: str = "Database operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500,
            details=details,
        )


class ConflictError(ForecastLabError):
    """Resource conflict error.

    Use when an operation conflicts with existing state (e.g., duplicate).
    Agents should check existing resources before retrying.
    """

    error_type_uri: str = ERROR_TYPES["CONFLICT"]

    def __init__(
        self,
        message: str = "Resource conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=409,
            details=details,
        )


class BadRequestError(ForecastLabError):
    """Bad request error.

    Use when the request is malformed or invalid.
    Agents should check the request format and parameters.
    """

    error_type_uri: str = ERROR_TYPES["BAD_REQUEST"]

    def __init__(
        self,
        message: str = "Bad request",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="BAD_REQUEST",
            status_code=400,
            details=details,
        )


# =============================================================================
# Exception Handlers (RFC 7807)
# =============================================================================


async def forecastlab_exception_handler(
    _request: Request,
    exc: ForecastLabError,
) -> ProblemDetailResponse:
    """Handle ForecastLabError exceptions with RFC 7807 Problem Details.

    Args:
        _request: FastAPI request object.
        exc: The raised exception.

    Returns:
        RFC 7807 Problem Detail response.
    """
    logger.error(
        "app.error_handled",
        error=exc.message,
        error_type=type(exc).__name__,
        error_code=exc.code,
        status_code=exc.status_code,
        details=exc.details,
        exc_info=True,
    )

    return problem_response(
        status=exc.status_code,
        title=exc.title,
        detail=exc.message,
        error_code=exc.code,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> ProblemDetailResponse:
    """Handle Pydantic validation errors with RFC 7807 Problem Details.

    Converts Pydantic validation errors to the 'errors' extension field
    so agents can identify which specific fields need correction.

    Args:
        request: FastAPI request object.
        exc: Pydantic validation error.

    Returns:
        RFC 7807 Problem Detail response with field-level errors.
    """
    # Convert Pydantic errors to RFC 7807 format
    field_errors: list[dict[str, str]] = []
    for error in exc.errors():
        loc = error.get("loc", [])
        field_path = ".".join(str(part) for part in loc if part != "body")
        field_errors.append(
            {
                "field": field_path,
                "message": str(error.get("msg", "Validation failed")),
                "type": str(error.get("type", "unknown")),
            }
        )

    logger.warning(
        "app.validation_error",
        error_count=len(field_errors),
        path=str(request.url.path),
        fields=[e["field"] for e in field_errors],
    )

    return problem_response(
        status=422,
        title="Validation Error",
        detail=f"Request validation failed with {len(field_errors)} error(s). "
        "Check the 'errors' field for details.",
        error_code="VALIDATION_ERROR",
        errors=field_errors,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> ProblemDetailResponse:
    """Handle unexpected exceptions with RFC 7807 Problem Details.

    Args:
        request: FastAPI request object.
        exc: The raised exception.

    Returns:
        RFC 7807 Problem Detail response.
    """
    logger.error(
        "app.unhandled_error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url.path),
        exc_info=True,
    )

    return problem_response(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred. Please try again later or "
        "contact support with the request_id.",
        error_code="INTERNAL_ERROR",
    )


# =============================================================================
# Handler Registration
# =============================================================================


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with FastAPI app.

    All handlers return RFC 7807 Problem Details responses.

    Args:
        app: FastAPI application instance.
    """
    app.add_exception_handler(ForecastLabError, forecastlab_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
