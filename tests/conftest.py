"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from breakthevibe.web.app import create_app


@pytest.fixture()
def app():
    """Create a fresh app instance for tests."""
    return create_app()


@pytest.fixture()
async def authed_client(app):
    """An AsyncClient with a valid session cookie for authenticated API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login to get session cookie
        await client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpass"},
        )
        yield client
