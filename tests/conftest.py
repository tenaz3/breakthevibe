"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import Organization, _utc_now


@pytest.fixture()
def app():
    """Create a fresh app instance for tests."""
    # Ensure admin credentials are available for authenticated test fixtures
    os.environ.setdefault("ADMIN_USERNAME", "testuser")
    os.environ.setdefault("ADMIN_PASSWORD", "testpass")

    # Clear cached settings so env vars are picked up
    from breakthevibe.config.settings import get_settings

    get_settings.cache_clear()

    from breakthevibe.web.app import create_app

    return create_app()


@pytest.fixture()
async def authed_client(app):
    """An AsyncClient with a valid session cookie for authenticated API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login to get session cookie
        resp = await client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpass"},
        )
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
        yield client


@pytest.fixture()
async def async_engine():
    """In-memory SQLite engine with all tables created + sentinel org."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Bootstrap sentinel organization (required by user repo FK)
    from sqlmodel.ext.asyncio.session import AsyncSession

    async with AsyncSession(engine) as session:
        session.add(
            Organization(
                id=SENTINEL_ORG_ID,
                name="Default Organization",
                plan="free",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
        )
        await session.commit()

    yield engine
    await engine.dispose()
