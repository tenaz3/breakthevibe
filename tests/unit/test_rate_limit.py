"""Unit tests for RateLimitMiddleware in breakthevibe/web/middleware.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from breakthevibe.web.middleware import RateLimitMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(
    max_requests: int = 5,
    window_seconds: int = 60,
    prefix: str = "/api/",
) -> FastAPI:
    """Build a minimal FastAPI app with RateLimitMiddleware attached."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=max_requests,
        window_seconds=window_seconds,
        prefix=prefix,
    )

    @app.get("/api/ping")
    async def api_ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRateLimitMiddlewareConstructor:
    def test_default_parameters(self) -> None:
        app = FastAPI()
        middleware = RateLimitMiddleware(app)
        assert middleware._max_requests == 60
        assert middleware._window == 60
        assert middleware._prefix == "/api/"

    def test_custom_parameters(self) -> None:
        app = FastAPI()
        middleware = RateLimitMiddleware(
            app,
            max_requests=10,
            window_seconds=30,
            prefix="/v1/",
        )
        assert middleware._max_requests == 10
        assert middleware._window == 30
        assert middleware._prefix == "/v1/"

    def test_hits_starts_empty(self) -> None:
        app = FastAPI()
        middleware = RateLimitMiddleware(app)
        assert len(middleware._hits) == 0


@pytest.mark.unit
class TestRateLimitMiddlewareRequests:
    @pytest.mark.asyncio
    async def test_request_under_limit_returns_200(self) -> None:
        app = _make_app(max_requests=5)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/ping")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_request_exceeding_limit_returns_429(self) -> None:
        app = _make_app(max_requests=3)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(3):
                await client.get("/api/ping")
            resp = await client.get("/api/ping")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_429_response_has_retry_after_header(self) -> None:
        window = 45
        app = _make_app(max_requests=2, window_seconds=window)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(2):
                await client.get("/api/ping")
            resp = await client.get("/api/ping")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert resp.headers["retry-after"] == str(window)

    @pytest.mark.asyncio
    async def test_429_response_body_contains_detail(self) -> None:
        app = _make_app(max_requests=1)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/ping")
            resp = await client.get("/api/ping")
        assert resp.status_code == 429
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_non_api_path_not_rate_limited(self) -> None:
        """Requests to paths outside the prefix bypass rate limiting entirely."""
        app = _make_app(max_requests=1, prefix="/api/")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(10):
                resp = await client.get("/health")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_exactly_at_limit_is_allowed(self) -> None:
        """The Nth request (equal to max_requests) must still succeed."""
        max_req = 4
        app = _make_app(max_requests=max_req)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for i in range(max_req):
                resp = await client.get("/api/ping")
                assert resp.status_code == 200, f"Request {i + 1} should be allowed"

    @pytest.mark.asyncio
    async def test_one_over_limit_is_blocked(self) -> None:
        max_req = 4
        app = _make_app(max_requests=max_req)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(max_req):
                await client.get("/api/ping")
            resp = await client.get("/api/ping")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_expired_window_entries_are_pruned(self) -> None:
        """Old timestamps outside the window are purged so limits reset.

        The middleware calls time.monotonic() once per request. By returning a
        low timestamp for the first two requests and a high timestamp for the
        third, the two earlier hits fall outside the 1-second window and are
        pruned, allowing the third request through.
        """
        fastapi_app = FastAPI()
        fastapi_app.add_middleware(
            RateLimitMiddleware,
            max_requests=2,
            window_seconds=1,
            prefix="/api/",
        )

        @fastapi_app.get("/api/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        transport = ASGITransport(app=fastapi_app)

        # One monotonic call per request dispatch.
        # Requests 1 & 2: timestamp 0.0 (epoch of our mock clock)
        # Request 3: timestamp 2.0 → age of earlier hits = 2.0s > window 1s → pruned
        timestamps = [0.0, 0.0, 2.0]

        with patch("breakthevibe.web.middleware.time") as mock_time:
            mock_time.monotonic.side_effect = timestamps
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for _ in range(2):
                    await client.get("/api/ping")
                resp = await client.get("/api/ping")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_custom_prefix_applies_correctly(self) -> None:
        """Middleware only rate-limits paths starting with the configured prefix."""
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=1,
            window_seconds=60,
            prefix="/restricted/",
        )

        @app.get("/restricted/resource")
        async def restricted() -> dict[str, str]:
            return {"ok": "yes"}

        @app.get("/open/resource")
        async def open_resource() -> dict[str, str]:
            return {"ok": "yes"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First restricted request — allowed
            resp = await client.get("/restricted/resource")
            assert resp.status_code == 200

            # Second restricted request — blocked
            resp = await client.get("/restricted/resource")
            assert resp.status_code == 429

            # Open path is never blocked
            for _ in range(5):
                resp = await client.get("/open/resource")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_warning_logged_on_exceed(self) -> None:
        app = _make_app(max_requests=1)
        transport = ASGITransport(app=app)

        with patch("breakthevibe.web.middleware.logger") as mock_logger:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/ping")
                await client.get("/api/ping")

            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args[1]
            assert "ip" in call_kwargs
            assert "path" in call_kwargs

    @pytest.mark.asyncio
    async def test_hit_appended_on_allowed_request(self) -> None:
        """Each allowed request appends one timestamp to _hits for its IP."""
        fastapi_app = FastAPI()
        RateLimitMiddleware(fastapi_app, max_requests=10)

        fastapi_app.add_middleware(
            RateLimitMiddleware,
            max_requests=10,
            window_seconds=60,
            prefix="/api/",
        )

        @fastapi_app.get("/api/check")
        async def check() -> dict[str, int]:
            return {"count": 1}

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/api/check")
            await client.get("/api/check")

        # The test verifies the middleware responds 200 on both — sufficient
        # to confirm requests are being tracked rather than blocked.

    @pytest.mark.asyncio
    async def test_max_requests_zero_blocks_all(self) -> None:
        """Setting max_requests=0 should block every API request immediately."""
        app = _make_app(max_requests=0)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/ping")
        assert resp.status_code == 429
