"""RFC 7807 Problem Details for HTTP APIs.

This module implements the RFC 7807 standard for machine-readable error responses,
enabling LLM agents to automatically diagnose and troubleshoot API errors.

Reference: https://datatracker.ietf.org/doc/html/rfc7807
"""

from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


# =============================================================================
# Error Type URIs
# =============================================================================

# Base URI for error types (relative URIs for portability)
ERROR_TYPE_BASE = "/errors"

ERROR_TYPES = {
    "NOT_FOUND": f"{ERROR_TYPE_BASE}/not-found",
    "VALIDATION_ERROR": f"{ERROR_TYPE_BASE}/validation",
    "DATABASE_ERROR": f"{ERROR_TYPE_BASE}/database",
    "CONFLICT": f"{ERROR_TYPE_BASE}/conflict",
    "UNAUTHORIZED": f"{ERROR_TYPE_BASE}/unauthorized",
    "FORBIDDEN": f"{ERROR_TYPE_BASE}/forbidden",
    "RATE_LIMITED": f"{ERROR_TYPE_BASE}/rate-limited",
    "INTERNAL_ERROR": f"{ERROR_TYPE_BASE}/internal",
    "BAD_REQUEST": f"{ERROR_TYPE_BASE}/bad-request",
    "SERVICE_UNAVAILABLE": f"{ERROR_TYPE_BASE}/service-unavailable",
}


# =============================================================================
# Problem Detail Schema
# =============================================================================


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.

    This schema enables machine-readable error responses that LLM agents
    can use for automatic troubleshooting and retry logic.

    Attributes:
        type: URI identifying the error type (for categorization).
        title: Short human-readable summary of the problem.
        status: HTTP status code.
        detail: Human-readable explanation specific to this occurrence.
        instance: URI reference for this specific problem occurrence.
        errors: Optional field-level validation errors (extension for 422).
        code: Machine-readable error code (extension for backwards compatibility).
        request_id: Request correlation ID (extension for tracing).
    """

    model_config = ConfigDict(extra="allow")  # Allow extensions per RFC 7807

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type. "
        "Use this to categorize errors for automated handling.",
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem type. "
        "Should be the same for all occurrences of this problem type.",
    )
    status: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code for this occurrence.",
    )
    detail: str | None = Field(
        None,
        description="Human-readable explanation specific to this occurrence. "
        "Provides context beyond the title.",
    )
    instance: str | None = Field(
        None,
        description="URI reference for this specific problem occurrence. "
        "Use for error tracking and correlation.",
    )
    # Extensions
    errors: list[dict[str, Any]] | None = Field(
        None,
        description="Field-level validation errors. Present for 422 responses "
        "to help agents identify which fields need correction.",
    )
    code: str | None = Field(
        None,
        description="Machine-readable error code for backwards compatibility. "
        "Maps to internal error categories.",
    )
    request_id: str | None = Field(
        None,
        description="Request correlation ID for distributed tracing. Include in support requests.",
    )


# =============================================================================
# Problem Detail Response
# =============================================================================


class ProblemDetailResponse(JSONResponse):
    """JSON response with RFC 7807 content type.

    Sets the proper media type for problem details responses.
    """

    media_type = "application/problem+json"


# =============================================================================
# Helper Functions
# =============================================================================


def create_problem_detail(
    status: int,
    title: str,
    detail: str | None = None,
    error_code: str = "INTERNAL_ERROR",
    errors: list[dict[str, Any]] | None = None,
) -> ProblemDetail:
    """Create a ProblemDetail instance with proper type URI and instance.

    Args:
        status: HTTP status code.
        title: Short problem summary.
        detail: Detailed explanation (optional).
        error_code: Internal error code for type URI lookup.
        errors: Field-level validation errors (optional).
    Returns:
        Configured ProblemDetail instance.
    """
    request_id = request_id_ctx.get()

    problem = ProblemDetail(
        type=ERROR_TYPES.get(error_code, f"{ERROR_TYPE_BASE}/{error_code.lower()}"),
        title=title,
        status=status,
        detail=detail,
        instance=f"/requests/{request_id}" if request_id else None,
        errors=errors,
        code=error_code,
        request_id=request_id,
    )

    return problem


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    error_code: str = "INTERNAL_ERROR",
    errors: list[dict[str, Any]] | None = None,
) -> ProblemDetailResponse:
    """Create a ProblemDetailResponse with proper content type.

    Args:
        status: HTTP status code.
        title: Short problem summary.
        detail: Detailed explanation (optional).
        error_code: Internal error code for type URI lookup.
        errors: Field-level validation errors (optional).
    Returns:
        JSONResponse with problem+json content type.
    """
    problem = create_problem_detail(
        status=status,
        title=title,
        detail=detail,
        error_code=error_code,
        errors=errors,
    )

    return ProblemDetailResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
    )


# =============================================================================
# Exception Handlers for RFC 7807
# =============================================================================
