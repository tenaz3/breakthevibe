"""Async database engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import get_settings


def get_engine():  # noqa: ANN201
    """Create async database engine from settings."""
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=settings.debug)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    engine = get_engine()
    async with AsyncSession(engine) as session:
        yield session


async def init_db() -> None:
    """Create all tables (for dev/testing only; use Alembic in production)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
