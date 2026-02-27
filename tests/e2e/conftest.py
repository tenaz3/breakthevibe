"""E2E test fixtures — full app with authenticated client.

IMPORTANT: Run E2E tests with USE_DATABASE=false to avoid async engine
event loop conflicts:

    USE_DATABASE=false uv run pytest tests/e2e/ -v

The module-level repo singletons in dependencies.py bind to the import-time
event loop, which differs from pytest's per-test loop. When the parent
tests/conftest.py imports create_app at the top level, it initializes these
singletons before any e2e-level conftest hooks can run.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure USE_DATABASE is false when running e2e tests standalone
os.environ.setdefault("USE_DATABASE", "false")


@pytest.fixture()
def app():
    """Create a fresh app instance for E2E tests."""
    from breakthevibe.web.app import create_app

    return create_app()


@pytest.fixture()
async def client(app):
    """Unauthenticated async client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture()
async def authed_client(app):
    """Authenticated async client with valid session cookie."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpass"},
        )
        yield c
