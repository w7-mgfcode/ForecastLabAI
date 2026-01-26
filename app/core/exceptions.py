"""Custom exceptions and FastAPI exception handlers."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class ForecastLabError(Exception):
    """Base exception for ForecastLabAI application errors."""

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


class NotFoundError(ForecastLabError):
    """Resource not found error."""

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
    """Input validation error."""

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
    """Database operation error."""

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


async def forecastlab_exception_handler(
    _request: Request,
    exc: ForecastLabError,
) -> JSONResponse:
    """Handle ForecastLabError exceptions.

    Args:
        request: FastAPI request object.
        exc: The raised exception.

    Returns:
        JSON response with error details.
    """
    request_id = request_id_ctx.get()

    logger.error(
        "app.error_handled",
        error=exc.message,
        error_type=type(exc).__name__,
        error_code=exc.code,
        status_code=exc.status_code,
        details=exc.details,
        exc_info=True,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions.

    Args:
        request: FastAPI request object.
        exc: The raised exception.

    Returns:
        JSON response with generic error.
    """
    request_id = request_id_ctx.get()

    logger.error(
        "app.unhandled_error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url.path),
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with FastAPI app.

    Args:
        app: FastAPI application instance.
    """
    app.add_exception_handler(ForecastLabError, forecastlab_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
