"""Database-backed test case repository for caching generated tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import TestCase
from breakthevibe.models.domain import GeneratedTestCase, TestStep
from breakthevibe.types import TestCategory

logger = structlog.get_logger(__name__)


class TestCaseRepository:
    """PostgreSQL-backed test case cache."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save_batch(
        self,
        project_id: int,
        org_id: str,
        crawl_run_id: int | None,
        sitemap_hash: str,
        cases: list[GeneratedTestCase],
    ) -> int:
        """Delete existing cases for project, insert new batch. Returns count saved."""
        async with AsyncSession(self._engine) as session:
            # Delete existing cached cases for this project
            await session.execute(
                delete(TestCase).where(
                    col(TestCase.project_id) == project_id,
                    col(TestCase.org_id) == org_id,
                )
            )
            # Insert new batch
            for case in cases:
                steps_data = json.dumps([step.model_dump() for step in case.steps], default=str)
                row = TestCase(
                    org_id=org_id,
                    project_id=project_id,
                    crawl_run_id=crawl_run_id,
                    name=case.name,
                    category=case.category.value,
                    description=case.description,
                    route_path=case.route,
                    steps_json=steps_data,
                    code=case.code or None,
                    sitemap_hash=sitemap_hash,
                )
                session.add(row)
            await session.commit()
            logger.info(
                "test_cases_cached",
                project_id=project_id,
                count=len(cases),
                sitemap_hash=sitemap_hash,
            )
            return len(cases)

    async def load_for_project(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> list[GeneratedTestCase]:
        """Return cached GeneratedTestCase objects, or [] if none exist."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(TestCase)
                .where(
                    col(TestCase.project_id) == project_id,
                    col(TestCase.org_id) == org_id,
                )
                .order_by(TestCase.id)  # type: ignore[attr-defined]
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            cases: list[GeneratedTestCase] = []
            for row in rows:
                steps: list[TestStep] = []
                if row.steps_json:
                    try:
                        raw_steps = json.loads(row.steps_json)
                        steps = [TestStep.model_validate(s) for s in raw_steps]
                    except (json.JSONDecodeError, ValueError):
                        logger.warning("invalid_steps_json", test_case_id=row.id)
                        continue
                cases.append(
                    GeneratedTestCase(
                        name=row.name,
                        category=TestCategory(row.category),
                        description=row.description,
                        route=row.route_path,
                        steps=steps,
                        code=row.code or "",
                    )
                )
            return cases

    async def get_cache_meta(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> dict[str, Any] | None:
        """Return {sitemap_hash, updated_at, count} or None if no cache."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(TestCase)
                .where(
                    col(TestCase.project_id) == project_id,
                    col(TestCase.org_id) == org_id,
                )
                .order_by(TestCase.updated_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            )
            result = await session.execute(stmt)
            latest = result.scalars().first()
            if not latest:
                return None

            # Count total
            count_stmt = select(TestCase).where(
                col(TestCase.project_id) == project_id,
                col(TestCase.org_id) == org_id,
            )
            count_result = await session.execute(count_stmt)
            count = len(count_result.scalars().all())

            return {
                "sitemap_hash": latest.sitemap_hash,
                "updated_at": latest.updated_at,
                "count": count,
            }

    async def delete_for_project(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> None:
        """Hard-delete all cached test cases for a project."""
        async with AsyncSession(self._engine) as session:
            await session.execute(
                delete(TestCase).where(
                    col(TestCase.project_id) == project_id,
                    col(TestCase.org_id) == org_id,
                )
            )
            await session.commit()
            logger.info("test_cases_deleted", project_id=project_id)
