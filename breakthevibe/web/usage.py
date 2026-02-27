"""Usage enforcement for billing plan limits."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException
from sqlalchemy import text

from breakthevibe.billing.plans import UNLIMITED, get_plan_limits
from breakthevibe.config.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

# Metric-to-limit mapping
_METRIC_LIMIT_MAP = {
    "projects": "max_projects",
    "crawls": "max_crawls_per_month",
    "test_runs": "max_test_runs_per_month",
}


class UsageEnforcer:
    """Checks and increments usage counters against plan limits.

    Uses atomic INSERT ON CONFLICT DO UPDATE to prevent race conditions (C-5).
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self, org_id: str, metric: str, plan: str = "free") -> None:
        """Check if the org is within usage limits for the given metric.

        Raises HTTPException(429) if limit exceeded.
        Skips enforcement in single-tenant mode (H-6).
        """
        settings = get_settings()
        if settings.auth_mode == "single":
            return

        limits = get_plan_limits(plan)
        limit_attr = _METRIC_LIMIT_MAP.get(metric)
        if not limit_attr:
            return

        limit_value = getattr(limits, limit_attr)
        if limit_value == UNLIMITED:
            return

        period = _current_period()
        current = await self._get_count(org_id, metric, period)

        if current >= limit_value:
            logger.warning(
                "usage_limit_exceeded",
                org_id=org_id,
                metric=metric,
                current=current,
                limit=limit_value,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Plan limit exceeded for {metric}. "
                f"Current: {current}, limit: {limit_value}. "
                "Upgrade your plan to continue.",
            )

    async def increment(self, org_id: str, metric: str) -> int:
        """Atomically increment a usage counter and return new count.

        Uses INSERT ... ON CONFLICT DO UPDATE SET count = count + 1 (C-5).
        """
        period = _current_period()
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "INSERT INTO usage_records "
                    "(org_id, metric, period, count, created_at, updated_at) "
                    "VALUES (:org_id, :metric, :period, 1, NOW(), NOW()) "
                    "ON CONFLICT (org_id, metric, period) "
                    "DO UPDATE SET count = usage_records.count + 1, "
                    "updated_at = NOW() RETURNING count"
                ),
                {"org_id": org_id, "metric": metric, "period": period},
            )
            row = result.fetchone()
            new_count = row[0] if row else 1
        logger.debug("usage_incremented", org_id=org_id, metric=metric, count=new_count)
        return int(new_count)

    async def _get_count(self, org_id: str, metric: str, period: str) -> int:
        """Get current usage count for an org/metric/period."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count FROM usage_records "
                    "WHERE org_id = :org_id AND metric = :metric AND period = :period"
                ),
                {"org_id": org_id, "metric": metric, "period": period},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0


def _current_period() -> str:
    """Get current billing period as YYYY-MM string."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m")
