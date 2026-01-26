"""Tests for logging configuration."""

from app.core.logging import configure_logging, get_logger, request_id_ctx


def test_get_logger_returns_bound_logger():
    """get_logger should return a structlog logger."""
    configure_logging()
    logger = get_logger("test")

    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")


def test_request_id_context_variable():
    """request_id_ctx should store and retrieve values."""
    assert request_id_ctx.get() is None

    token = request_id_ctx.set("test-id-123")
    assert request_id_ctx.get() == "test-id-123"

    request_id_ctx.reset(token)
    assert request_id_ctx.get() is None


def test_configure_logging_completes():
    """configure_logging should complete without error."""
    configure_logging()  # Should not raise
