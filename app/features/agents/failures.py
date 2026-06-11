"""Classify provider-API model failures into secret-safe, actionable details.

When every model in the PydanticAI ``FallbackModel`` chain fails (or a single
configured model fails with a provider error), the raw exception surface is an
opaque one-liner (``All models from FallbackModel failed (2 sub-exceptions)``)
and ``str(ModelHTTPError)`` embeds the provider response body verbatim — a
secret-leak risk. This module turns that exception tree into a list of
:class:`ModelFailureDetail` entries plus a deterministic human summary that the
chat UI renders as-is (issue #335).

Pure functions only — fully unit-testable without a DB or network.
"""

from __future__ import annotations

import re

from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models.fallback import ResponseRejected

from app.features.agents.schemas import FailureReason, ModelFailureDetail

# Secret-shaped substrings scrubbed from any surfaced provider message.
# Issue #335 hard constraint: no API keys / Bearer tokens, ever.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),  # Google API keys
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),  # OpenAI/Anthropic-style keys
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),  # Authorization bearer tokens
    re.compile(r"(?i)(api[_-]?key|token|authorization)[=:]\s*\S+"),
)

# Cap on the surfaced per-model detail string.
_MAX_DETAIL_LEN = 300

# Placeholder model names for failures that carry none.
_RESPONSE_REJECTED_MODEL = "(response rejected)"
_UNKNOWN_MODEL = "(unknown model)"

# Human labels for the summary string (rendered verbatim by the chat UI).
_REASON_LABELS: dict[FailureReason, str] = {
    "model_not_found": "model not found / invalid model name",
    "quota_exhausted": "quota or rate limit exhausted",
    "auth_error": "authentication/permission error",
    "provider_unavailable": "provider unavailable",
    "provider_error": "provider error",
    "response_rejected": "response rejected",
    "unknown": "unexpected failure",
}


def _sanitize(text: str) -> str:
    """Scrub secret-shaped substrings, then truncate to the detail cap."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text[:_MAX_DETAIL_LEN]


def _provider_message(body: object | None) -> str:
    """Extract the provider's human message from an HTTP error body.

    Handles the Google/OpenAI ``{"error": {"message": ...}}`` shape; a plain
    string passes through; anything else is stringified. Callers MUST pass the
    result through :func:`_sanitize` before surfacing it.
    """
    if body is None:
        return ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
    if isinstance(body, str):
        return body
    return str(body)


def _classify_http_status(status_code: int) -> FailureReason:
    """Map an HTTP status to the issue #335 reason taxonomy."""
    if status_code == 404:
        return "model_not_found"
    if status_code == 429:
        return "quota_exhausted"
    if status_code in (401, 403):
        return "auth_error"
    if status_code >= 500:
        return "provider_unavailable"
    return "provider_error"


def classify_model_failures(exc: BaseException) -> list[ModelFailureDetail]:
    """Flatten an exception (group) into classified per-model failures.

    ``FallbackExceptionGroup.exceptions`` is a tuple and sub-groups can nest —
    recurse into groups and classify only the leaves, preserving leg order.
    """
    if isinstance(exc, BaseExceptionGroup):
        details: list[ModelFailureDetail] = []
        for member in exc.exceptions:
            details.extend(classify_model_failures(member))
        return details
    if isinstance(exc, ModelHTTPError):
        return [
            ModelFailureDetail(
                model_name=exc.model_name,
                status_code=exc.status_code,
                reason=_classify_http_status(exc.status_code),
                detail=_sanitize(_provider_message(exc.body)),
            )
        ]
    if isinstance(exc, ResponseRejected):
        return [
            ModelFailureDetail(
                model_name=_RESPONSE_REJECTED_MODEL,
                status_code=None,
                reason="response_rejected",
                detail=_sanitize(str(exc)),
            )
        ]
    if isinstance(exc, ModelAPIError):
        return [
            ModelFailureDetail(
                model_name=exc.model_name,
                status_code=None,
                reason="provider_error",
                detail=_sanitize(str(exc)),
            )
        ]
    return [
        ModelFailureDetail(
            model_name=_UNKNOWN_MODEL,
            status_code=None,
            reason="unknown",
            detail=_sanitize(str(exc)),
        )
    ]


def summarize_model_failures(failures: list[ModelFailureDetail]) -> str:
    """Build the deterministic human summary the chat UI renders verbatim.

    One failure → ``The configured agent model failed — {leg}``; several →
    ``All configured agent models failed — {leg}; {leg}; …`` where each leg is
    ``{model_name}: {label} (HTTP {status_code})`` (HTTP part omitted when the
    failure was not HTTP-shaped).
    """
    legs: list[str] = []
    for failure in failures:
        leg = f"{failure.model_name}: {_REASON_LABELS[failure.reason]}"
        if failure.status_code is not None:
            leg = f"{leg} (HTTP {failure.status_code})"
        legs.append(leg)
    joined = "; ".join(legs)
    if len(failures) == 1:
        return f"The configured agent model failed — {joined}"
    return f"All configured agent models failed — {joined}"
