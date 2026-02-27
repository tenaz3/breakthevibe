"""Shared test fixtures."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import Organization, _utc_now
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
