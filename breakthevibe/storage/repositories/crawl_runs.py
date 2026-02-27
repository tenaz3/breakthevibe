"""Database-backed crawl run repository."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import CrawlRun

logger = structlog.get_logger(__name__)


class CrawlRunRepository:
    """PostgreSQL-backed crawl run store."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_latest_sitemap(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> dict[str, Any]:
        """Return the latest sitemap for a project, or empty dict."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(CrawlRun)
                .where(
                    col(CrawlRun.project_id) == project_id,
                    col(CrawlRun.org_id) == org_id,
                    col(CrawlRun.site_map_json).is_not(None),
                )
                .order_by(CrawlRun.created_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            )
            result = await session.execute(stmt)
            crawl_run = result.scalars().first()

            if not crawl_run or not crawl_run.site_map_json:
                return {}

            try:
                return json.loads(crawl_run.site_map_json)  # type: ignore[no-any-return]
            except (json.JSONDecodeError, TypeError):
                logger.warning("invalid_sitemap_json", project_id=project_id)
                return {}
