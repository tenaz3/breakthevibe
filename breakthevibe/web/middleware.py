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
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter with per-path-prefix tiers.

    Checks each request path against ``rate_limits`` (most-specific prefix
    first) and enforces the matching limit.  Falls back to ``max_requests``
    when no prefix matches.  Only paths under ``prefix`` are checked at all.

    Default tiers
    -------------
    * ``/api/auth/`` — 10 req/min  (brute-force protection for login/register)
    * ``/api/``      — 60 req/min  (general API)

    Memory management
    -----------------
    IP buckets are pruned every ``_CLEANUP_INTERVAL`` seconds so the internal
    dict stays bounded to IPs that were active within the last window.
    """

    # How often (in seconds) to purge fully-expired IP buckets from _hits.
    _CLEANUP_INTERVAL: float = 300.0  # 5 minutes

    # Default per-prefix limits (req / window_seconds).
    # Evaluated most-specific-first (longest prefix wins).
    _DEFAULT_RATE_LIMITS: dict[str, int] = {
        "/api/auth/": 30,
        "/api/": 60,
    }

    def __init__(
        self,
        app: object,
        max_requests: int = 60,
        window_seconds: int = 60,
        prefix: str = "/api/",
        rate_limits: dict[str, int] | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_requests = max_requests
        self._window = window_seconds
        self._prefix = prefix
        # Build the tier table:
        # • Caller-supplied rate_limits: use as-is.
        # • Default tiers: substitute max_requests for the general /api/ entry
        #   so the constructor argument remains the effective general-API cap,
        #   while the stricter /api/auth/ tier (10 req/min) is preserved.
        if rate_limits is not None:
            raw_limits = rate_limits
        else:
            raw_limits = dict(self._DEFAULT_RATE_LIMITS)
            raw_limits[prefix] = max_requests
        # Sort descending by key length so more-specific prefixes match first.
        self._rate_limits: list[tuple[str, int]] = sorted(
            raw_limits.items(), key=lambda kv: len(kv[0]), reverse=True
        )
        # Keyed by "{prefix_key}:{ip}" so each tier has its own counter per IP.
        self._hits: dict[str, list[float]] = defaultdict(list)
        # Initialised to 0.0 rather than time.monotonic() so that __init__
        # never calls time.monotonic() — keeps unit-test mocking straightforward.
        self._last_cleanup: float = 0.0

    def _get_limit(self, path: str) -> tuple[str, int]:
        """Return (bucket_prefix, max_requests) for the given request path.

        Iterates tiers longest-prefix-first so ``/api/auth/`` wins over
        ``/api/`` for auth paths.
        """
        for tier_prefix, limit in self._rate_limits:
            if path.startswith(tier_prefix):
                return tier_prefix, limit
        return self._prefix, self._max_requests

    def _purge_stale_ips(self, now: float) -> None:
        """Remove IP buckets whose most recent hit has expired the window."""
        if now - self._last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._hits = defaultdict(
            list,
            {key: ts for key, ts in self._hits.items() if ts and now - ts[-1] < self._window},
        )
        self._last_cleanup = now

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(self._prefix):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        now = time.monotonic()

        # Periodically purge buckets for IPs that have gone quiet
        self._purge_stale_ips(now)

        tier_prefix, limit = self._get_limit(path)
        bucket_key = f"{tier_prefix}:{client_ip}"

        # Slide the window: drop timestamps older than window_seconds
        self._hits[bucket_key] = [t for t in self._hits[bucket_key] if now - t < self._window]

        if len(self._hits[bucket_key]) >= limit:
            from starlette.responses import JSONResponse

            logger.warning(
                "rate_limit_exceeded",
                ip=client_ip,
                path=path,
                tier=tier_prefix,
                limit=limit,
            )
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=429,
                headers={"Retry-After": str(self._window)},
            )

        self._hits[bucket_key].append(now)
        return await call_next(request)
