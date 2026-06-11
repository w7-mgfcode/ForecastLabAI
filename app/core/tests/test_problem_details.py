"""Unit tests for RFC 7807 problem_response extension members (issue #335).

The `extensions` channel lets a ForecastLabError surface client-safe data
(e.g. classified per-model failures) in the problem+json body without going
through the log-only `details` attribute.
"""

import json
from typing import Any

from app.core.problem_details import problem_response


def _body(response: Any) -> dict[str, Any]:
    """Decode a ProblemDetailResponse body."""
    decoded: dict[str, Any] = json.loads(response.body)
    return decoded


def test_problem_response_without_extensions_unchanged() -> None:
    """Default (no extensions) output keeps the existing shape exactly."""
    response = problem_response(
        status=404,
        title="Not Found",
        detail="Resource not found",
        error_code="NOT_FOUND",
    )

    body = _body(response)
    assert response.status_code == 404
    assert body["status"] == 404
    assert body["code"] == "NOT_FOUND"
    assert body["type"] == "/errors/not-found"
    assert "failures" not in body


def test_problem_response_merges_extensions() -> None:
    """Extension members are merged into the serialized body."""
    response = problem_response(
        status=502,
        title="Agent Fallback Exhausted",
        detail="All configured agent models failed",
        error_code="AGENT_FALLBACK_EXHAUSTED",
        extensions={"failures": [{"model_name": "m1", "reason": "model_not_found"}]},
    )

    body = _body(response)
    assert body["code"] == "AGENT_FALLBACK_EXHAUSTED"
    assert body["type"] == "/errors/agent-fallback-exhausted"
    assert body["failures"] == [{"model_name": "m1", "reason": "model_not_found"}]


def test_problem_response_extensions_cannot_override_reserved() -> None:
    """Reserved base-field keys in extensions are silently dropped."""
    response = problem_response(
        status=502,
        title="Agent Fallback Exhausted",
        detail="real detail",
        error_code="AGENT_FALLBACK_EXHAUSTED",
        extensions={
            "status": 200,
            "code": "HACK",
            "detail": "spoofed",
            "type": "about:blank",
            "title": "spoofed",
            "safe_key": "kept",
        },
    )

    body = _body(response)
    assert response.status_code == 502
    assert body["status"] == 502
    assert body["code"] == "AGENT_FALLBACK_EXHAUSTED"
    assert body["detail"] == "real detail"
    assert body["type"] == "/errors/agent-fallback-exhausted"
    assert body["title"] == "Agent Fallback Exhausted"
    assert body["safe_key"] == "kept"
