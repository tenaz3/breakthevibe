"""Health check endpoint logic."""

from __future__ import annotations

import structlog

from breakthevibe.config.settings import get_settings

logger = structlog.get_logger(__name__)


async def check_health() -> dict[str, object]:
    """Return application health status with DB probe."""
    settings = get_settings()
    result: dict[str, object] = {
        "status": "healthy",
        "version": "0.1.0",
        "auth_mode": settings.auth_mode,
        "database": "connected",
    }

    try:
        from sqlalchemy import text

        from breakthevibe.storage.database import get_engine

        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health_check_db_failed", error=str(exc))
        result["database"] = "unavailable"
        result["status"] = "degraded"

    return result
