"""Structured logging with structlog and request_id context."""

import logging
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.config import get_settings

# Context variable for request correlation
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def add_request_id(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Add request_id from context to log events."""
    request_id = request_id_ctx.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging() -> None:
    """Configure structlog for the application."""
    settings = get_settings()

    # Common processors (compatible with PrintLoggerFactory)
    shared_processors: list[structlog.types.Processor] = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_request_id,
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    """Get a configured logger instance.

    Args:
        name: Logger name (typically __name__ of the calling module).

    Returns:
        Configured structlog logger with request_id binding.
    """
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
