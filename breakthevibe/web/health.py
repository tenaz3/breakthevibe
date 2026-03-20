"""Health check endpoint logic."""

from __future__ import annotations

import importlib.metadata

import structlog

logger = structlog.get_logger(__name__)


def _get_version() -> str:
    """Return the installed package version, falling back to 'dev'."""
    try:
        return importlib.metadata.version("breakthevibe")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


async def check_health() -> dict[str, object]:
    """Return application health status with DB probe."""
    result: dict[str, object] = {
        "status": "healthy",
        "version": _get_version(),
        "database": "connected",
    }

    try:
        from sqlalchemy import text

        from breakthevibe.storage.database import get_engine

        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        # Broad catch: health checks must never raise — DB probe can fail with
        # SQLAlchemyError, asyncpg.PostgresError, OSError, or connection pool errors.
        logger.warning("health_check_db_failed", error=str(exc))
        result["database"] = "unavailable"
        result["status"] = "degraded"

    return result
