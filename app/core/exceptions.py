"""Custom exceptions and FastAPI exception handlers.

Implements RFC 7807 Problem Details for machine-readable error responses.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from app.core.logging import get_logger
from app.core.problem_details import (
    AGENT_FALLBACK_EXHAUSTED_CODE,
    EMBEDDING_AUTH_CODE,
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
        extensions: dict[str, Any] | None = None,
    ) -> None:
        """Initialize application error.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            status_code: HTTP status code.
            details: Additional error context. LOG-ONLY — the exception
                handler never copies it into the response body (it may carry
                internals).
            extensions: RFC 7807 extension members the handler DOES merge
                into the problem+json response body (#335). Only put
                client-safe, already-sanitized data here.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.extensions = extensions or {}

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


class UnprocessableEntityError(ForecastLabError):
    """Resource-state 422 error.

    Use when the request itself is well-formed and routable, but the targeted
    resource is in a state that prevents the operation from completing — e.g.,
    a registry run with no artifact saved yet, a saved bundle whose pickle
    references an optional ML extra that is not installed, or a bundle file
    that has been deleted from disk while the registry row lives on.

    Distinct from :class:`ValidationError` (``code="VALIDATION_ERROR"``), which
    is for Pydantic input failures. Consumers and tests disambiguate the two
    422s via the ``type`` URI in the RFC 7807 problem+json body.
    """

    error_type_uri: str = ERROR_TYPES["UNPROCESSABLE_ENTITY"]

    def __init__(
        self,
        message: str = "Resource state prevents the operation",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="UNPROCESSABLE_ENTITY",
            status_code=422,
            details=details,
        )


class GatewayTimeoutError(ForecastLabError):
    """504 — server's own internal drain or upstream wait exceeded its budget.

    Use when a bounded server-side wait (e.g., ``DELETE /batch/{batch_id}``
    draining in-flight children) exceeds its configured budget. Distinct from
    a 408 client-timeout: the client did not time out, the server's own
    drain budget did. The PRP-34 batch cancel path is the canonical caller.
    """

    error_type_uri: str = ERROR_TYPES["GATEWAY_TIMEOUT"]

    def __init__(
        self,
        message: str = "Operation drain exceeded budget",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="GATEWAY_TIMEOUT",
            status_code=504,
            details=details,
        )


class EmbeddingProviderAuthError(ForecastLabError):
    """502 — the embedding provider rejected the configured credentials.

    Raised when the RAG embedding provider returns an authentication/
    authorization failure (HTTP 401/403 — an invalid, placeholder, or
    unauthorized API key) rather than a transient connection/server failure.
    Keeps the public ``/rag`` status at 502 (an upstream/gateway failure from
    the caller's perspective) but emits a *machine-readable* ``EMBEDDING_AUTH``
    problem ``type``/``code`` so consumers — notably the showcase demo
    pipeline — can classify it and SKIP the knowledge phase gracefully instead
    of hard-failing (issue #329). Disambiguated from a generic embedding 502
    (bare ``{"detail": ...}``) via the ``type`` URI in the problem+json body,
    mirroring the :class:`UnprocessableEntityError` 422 precedent.
    """

    error_type_uri: str = ERROR_TYPES[EMBEDDING_AUTH_CODE]

    def __init__(
        self,
        message: str = "Embedding provider rejected the configured credentials",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=EMBEDDING_AUTH_CODE,
            status_code=502,
            details=details,
        )


class AgentFallbackExhaustedError(ForecastLabError):
    """502 — every model in the agent's fallback chain failed (issue #335).

    Raised when the PydanticAI ``FallbackModel`` chain (or a single configured
    model) fails with provider-API errors on every leg. Mirrors
    :class:`EmbeddingProviderAuthError`: keeps the public status at 502 (an
    upstream failure from the caller's perspective) and emits a
    *machine-readable* ``AGENT_FALLBACK_EXHAUSTED`` problem ``type``/``code``
    so clients can classify it. The per-model classified failures ride the
    response-visible ``extensions`` channel as a ``failures`` member —
    ``details`` stays log-only by design.
    """

    error_type_uri: str = ERROR_TYPES[AGENT_FALLBACK_EXHAUSTED_CODE]

    def __init__(
        self,
        message: str,
        failures: list[dict[str, Any]],
    ) -> None:
        """Initialize with the human summary and classified per-model legs.

        Args:
            message: Human-actionable summary (already secret-safe).
            failures: Serialized ``ModelFailureDetail`` dicts — sanitized
                upstream by the classifier; surfaced verbatim to the client.
        """
        super().__init__(
            message=message,
            code=AGENT_FALLBACK_EXHAUSTED_CODE,
            status_code=502,
            extensions={"failures": failures},
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
        extensions=exc.extensions or None,
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
