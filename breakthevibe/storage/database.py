"""Async database engine and session factory."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Return a cached async database engine (singleton per process)."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


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
