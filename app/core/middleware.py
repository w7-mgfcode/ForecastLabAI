"""Request middleware for correlation and logging."""

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject and propagate request IDs for correlation."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request with correlation ID.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/handler in chain.

        Returns:
            Response with X-Request-ID header.
        """
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Set in context for logging
        token = request_id_ctx.set(request_id)

        try:
            logger.info(
                "http.request_started",
                method=request.method,
                path=str(request.url.path),
                query=str(request.url.query) if request.url.query else None,
            )

            response = await call_next(request)

            logger.info(
                "http.request_completed",
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
