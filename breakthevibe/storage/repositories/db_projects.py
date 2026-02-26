"""Database-backed project repository using SQLModel + AsyncSession."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from breakthevibe.models.database import CrawlRun, Project, TestCase, TestResult, TestRun

logger = structlog.get_logger(__name__)


class DatabaseProjectRepository:
    """PostgreSQL-backed project store using SQLModel.

    Maintains the same dict-based interface as the in-memory version
    so routes and templates do not need to change.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def _to_dict(self, project: Project) -> dict[str, Any]:
        """Convert a Project ORM instance to a plain dict."""
        return {
            "id": str(project.id),
            "name": project.name,
            "url": project.url,
            "rules_yaml": project.config_yaml or "",
            "created_at": project.created_at.isoformat(),
            "last_run_at": None,
            "status": "created",
        }

    async def create(self, name: str, url: str, rules_yaml: str = "") -> dict[str, Any]:
        async with AsyncSession(self._engine) as session:
            project = Project(name=name, url=url, config_yaml=rules_yaml or None)
            session.add(project)
            await session.commit()
            await session.refresh(project)
            result = self._to_dict(project)
            logger.info("project_created", id=result["id"], name=name)
            return result

    async def list_all(self) -> list[dict[str, Any]]:
        async with AsyncSession(self._engine) as session:
            statement = select(Project).order_by(Project.created_at.desc())  # type: ignore[attr-defined]
            results = await session.execute(statement)
            return [self._to_dict(p) for p in results.scalars().all()]

    async def get(self, project_id: str) -> dict[str, Any] | None:
        try:
            pid = int(project_id)
        except (ValueError, TypeError):
            return None
        async with AsyncSession(self._engine) as session:
            project = await session.get(Project, pid)
            if not project:
                return None
            return self._to_dict(project)

    async def delete(self, project_id: str) -> bool:
        try:
            pid = int(project_id)
        except (ValueError, TypeError):
            return False
        async with AsyncSession(self._engine) as session:
            project = await session.get(Project, pid)
            if not project:
                return False

            # Delete child rows that reference this project (no DB cascade)
            run_ids_result = await session.execute(
                select(TestRun.id).where(TestRun.project_id == pid)
            )
            run_ids = [r for (r,) in run_ids_result.all()]
            if run_ids:
                await session.execute(
                    delete(TestResult).where(TestResult.test_run_id.in_(run_ids))  # type: ignore[union-attr]
                )
                await session.execute(delete(TestRun).where(TestRun.project_id == pid))

            await session.execute(delete(TestCase).where(TestCase.project_id == pid))

            crawl_ids_result = await session.execute(
                select(CrawlRun.id).where(CrawlRun.project_id == pid)
            )
            crawl_ids = [r for (r,) in crawl_ids_result.all()]
            if crawl_ids:
                from breakthevibe.models.database import Route

                await session.execute(
                    delete(Route).where(Route.crawl_run_id.in_(crawl_ids))  # type: ignore[union-attr]
                )
                await session.execute(delete(CrawlRun).where(CrawlRun.project_id == pid))

            await session.delete(project)
            await session.commit()
            logger.info("project_deleted", id=project_id)
            return True

    async def update(self, project_id: str, **updates: Any) -> dict[str, Any] | None:
        try:
            pid = int(project_id)
        except (ValueError, TypeError):
            return None
        async with AsyncSession(self._engine) as session:
            project = await session.get(Project, pid)
            if not project:
                return None
            if "name" in updates:
                project.name = updates["name"]
            if "url" in updates:
                project.url = updates["url"]
            if "rules_yaml" in updates:
                project.config_yaml = updates["rules_yaml"]
            session.add(project)
            await session.commit()
            await session.refresh(project)
            result = self._to_dict(project)
            # Merge extra non-DB fields into the result dict
            for key in ("status", "last_run_id", "last_run_at"):
                if key in updates:
                    result[key] = updates[key]
            return result
