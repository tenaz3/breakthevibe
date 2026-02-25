"""FastAPI middleware: request ID injection and rate limiting."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique X-Request-ID header to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter for API endpoints.

    Limits requests per IP to `max_requests` within `window_seconds`.
    Only applies to paths starting with the given prefix (default: /api/).
    """

    def __init__(
        self,
        app: object,
        max_requests: int = 60,
        window_seconds: int = 60,
        prefix: str = "/api/",
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_requests = max_requests
        self._window = window_seconds
        self._prefix = prefix
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(self._prefix):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Clean old entries
        self._hits[client_ip] = [t for t in self._hits[client_ip] if now - t < self._window]

        if len(self._hits[client_ip]) >= self._max_requests:
            from starlette.responses import JSONResponse

            logger.warning("rate_limit_exceeded", ip=client_ip, path=request.url.path)
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
                headers={"Retry-After": str(self._window)},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)
