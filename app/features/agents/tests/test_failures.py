"""Unit tests for the model-failure classifier (issue #335).

Covers the status-code classification matrix, exception-group recursion,
secret scrubbing, detail truncation, and the deterministic human summary.
"""

import pytest
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, ModelHTTPError
from pydantic_ai.models.fallback import ResponseRejected

from app.features.agents.failures import (
    classify_model_failures,
    summarize_model_failures,
)
from app.features.agents.schemas import ModelFailureDetail


class TestClassifyModelFailures:
    """Classification matrix for classify_model_failures."""

    @pytest.mark.parametrize(
        ("status_code", "expected_reason"),
        [
            (404, "model_not_found"),
            (429, "quota_exhausted"),
            (401, "auth_error"),
            (403, "auth_error"),
            (500, "provider_unavailable"),
            (503, "provider_unavailable"),
            (418, "provider_error"),
        ],
    )
    def test_http_status_matrix(self, status_code: int, expected_reason: str) -> None:
        """Each HTTP status maps to its issue #335 reason."""
        failures = classify_model_failures(ModelHTTPError(status_code, "test:model"))

        assert len(failures) == 1
        assert failures[0].model_name == "test:model"
        assert failures[0].status_code == status_code
        assert failures[0].reason == expected_reason

    def test_fallback_group_preserves_leg_order(self) -> None:
        """A 404 + 429 group yields two details in model order."""
        group = FallbackExceptionGroup(
            "All models from FallbackModel failed",
            [
                ModelHTTPError(404, "google-gla:gemini-3-flash-preview"),
                ModelHTTPError(429, "google-gla:gemini-2.5-flash"),
            ],
        )

        failures = classify_model_failures(group)

        assert len(failures) == 2
        assert failures[0].model_name == "google-gla:gemini-3-flash-preview"
        assert failures[0].reason == "model_not_found"
        assert failures[1].model_name == "google-gla:gemini-2.5-flash"
        assert failures[1].reason == "quota_exhausted"

    def test_nested_group_flattens_leaves(self) -> None:
        """Sub-groups inside the group are recursed into, not classified as legs."""
        inner = FallbackExceptionGroup(
            "inner",
            [ModelHTTPError(429, "inner:model")],
        )
        outer = FallbackExceptionGroup(
            "outer",
            [ModelHTTPError(404, "outer:model"), inner],
        )

        failures = classify_model_failures(outer)

        assert [f.model_name for f in failures] == ["outer:model", "inner:model"]
        assert [f.reason for f in failures] == ["model_not_found", "quota_exhausted"]

    def test_bare_model_api_error_is_provider_error(self) -> None:
        """A non-HTTP ModelAPIError (connection failure) → provider_error, no status."""
        failures = classify_model_failures(
            ModelAPIError("ollama:gemma4-agent", "connection refused")
        )

        assert len(failures) == 1
        assert failures[0].model_name == "ollama:gemma4-agent"
        assert failures[0].status_code is None
        assert failures[0].reason == "provider_error"

    def test_response_rejected_member(self) -> None:
        """A ResponseRejected group member classifies as response_rejected."""
        group = FallbackExceptionGroup(
            "All models from FallbackModel failed",
            [ResponseRejected(2)],
        )

        failures = classify_model_failures(group)

        assert len(failures) == 1
        assert failures[0].reason == "response_rejected"
        assert failures[0].status_code is None

    def test_unknown_exception_is_unknown(self) -> None:
        """Anything else inside the group classifies as unknown."""
        failures = classify_model_failures(RuntimeError("boom"))

        assert len(failures) == 1
        assert failures[0].reason == "unknown"
        assert failures[0].status_code is None
        assert "boom" in failures[0].detail

    @pytest.mark.parametrize(
        "secret",
        [
            "AIzaFakeKey1234567890abcdef",
            "sk-fakekey1234567890abcdef",
            "Bearer xyz.abc-123",
            "api_key=supersecretvalue",
        ],
    )
    def test_secret_scrubbed_from_detail(self, secret: str) -> None:
        """Secret-shaped substrings in the provider body never reach the detail."""
        exc = ModelHTTPError(
            429,
            "test:model",
            body={"error": {"message": f"quota exceeded for {secret} retry later"}},
        )

        failures = classify_model_failures(exc)

        assert "[redacted]" in failures[0].detail
        assert "AIzaFake" not in failures[0].detail
        assert "sk-fake" not in failures[0].detail
        assert "xyz.abc-123" not in failures[0].detail
        assert "supersecretvalue" not in failures[0].detail

    def test_detail_truncated_to_cap(self) -> None:
        """A 1000-char provider message is truncated to the 300-char cap."""
        exc = ModelHTTPError(
            500,
            "test:model",
            body={"error": {"message": "x" * 1000}},
        )

        failures = classify_model_failures(exc)

        assert len(failures[0].detail) <= 300

    def test_provider_message_string_body(self) -> None:
        """A plain-string body passes through (sanitized)."""
        failures = classify_model_failures(ModelHTTPError(404, "test:model", body="not found"))

        assert failures[0].detail == "not found"

    def test_provider_message_none_body(self) -> None:
        """A missing body yields an empty detail."""
        failures = classify_model_failures(ModelHTTPError(404, "test:model"))

        assert failures[0].detail == ""


class TestSummarizeModelFailures:
    """Deterministic summary shapes (rendered verbatim by the chat UI)."""

    def test_single_leg_shape(self) -> None:
        failures = [
            ModelFailureDetail(
                model_name="anthropic:claude-test",
                status_code=401,
                reason="auth_error",
            )
        ]

        summary = summarize_model_failures(failures)

        assert summary == (
            "The configured agent model failed — "
            "anthropic:claude-test: authentication/permission error (HTTP 401)"
        )

    def test_two_leg_shape(self) -> None:
        failures = [
            ModelFailureDetail(
                model_name="google-gla:gemini-3-flash-preview",
                status_code=404,
                reason="model_not_found",
            ),
            ModelFailureDetail(
                model_name="google-gla:gemini-2.5-flash",
                status_code=429,
                reason="quota_exhausted",
            ),
        ]

        summary = summarize_model_failures(failures)

        assert summary == (
            "All configured agent models failed — "
            "google-gla:gemini-3-flash-preview: model not found / invalid model name (HTTP 404); "
            "google-gla:gemini-2.5-flash: quota or rate limit exhausted (HTTP 429)"
        )

    def test_non_http_leg_omits_status(self) -> None:
        failures = [
            ModelFailureDetail(
                model_name="ollama:gemma4-agent",
                status_code=None,
                reason="provider_error",
            )
        ]

        summary = summarize_model_failures(failures)

        assert "(HTTP" not in summary
        assert "ollama:gemma4-agent: provider error" in summary
