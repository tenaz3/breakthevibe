"""Database-backed test run repository."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import TestRun

logger = structlog.get_logger(__name__)


class TestRunRepository:
    """PostgreSQL-backed test run store."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def _to_dict(self, run: TestRun) -> dict[str, Any]:
        """Convert a TestRun ORM row to the dict shape routes expect."""
        completed_stages: list[str] = []
        if run.completed_stages_json:
            completed_stages = json.loads(run.completed_stages_json)

        suites: list[dict[str, Any]] = []
        if run.suites_json:
            suites = json.loads(run.suites_json)

        heal_warnings: list[str] = []
        if run.heal_warnings_json:
            heal_warnings = json.loads(run.heal_warnings_json)

        success = run.status == "completed"
        return {
            "run_id": run.run_uuid,
            "success": success,
            "status": run.status,
            "completed_stages": completed_stages,
            "failed_stage": run.failed_stage,
            "error_message": run.error_message or "",
            "duration_seconds": run.duration_seconds or 0.0,
            "total": run.total,
            "passed": run.passed,
            "failed": run.failed,
            "healed": run.healed,
            "suites": suites,
            "heal_warnings": heal_warnings,
        }

    async def save_pipeline_result(
        self,
        project_id: int,
        org_id: str,
        result_data: dict[str, Any],
    ) -> TestRun:
        """Persist a pipeline result dict as a TestRun row."""
        completed_stages = result_data.get("completed_stages", [])
        suites = result_data.get("suites", [])
        heal_warnings = result_data.get("heal_warnings", [])

        run = TestRun(
            project_id=project_id,
            org_id=org_id,
            run_uuid=result_data.get("run_id"),
            status="completed" if result_data.get("success") else "failed",
            execution_mode="smart",
            total=result_data.get("total", 0),
            passed=result_data.get("passed", 0),
            failed=result_data.get("failed", 0),
            completed_stages_json=json.dumps(completed_stages) if completed_stages else None,
            failed_stage=result_data.get("failed_stage"),
            error_message=result_data.get("error_message"),
            duration_seconds=result_data.get("duration_seconds"),
            suites_json=json.dumps(suites) if suites else None,
            heal_warnings_json=json.dumps(heal_warnings) if heal_warnings else None,
        )

        async with AsyncSession(self._engine) as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
            logger.info(
                "test_run_saved",
                id=run.id,
                project_id=project_id,
                org_id=org_id,
                run_uuid=run.run_uuid,
            )
            return run

    async def get_latest_for_project(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> dict[str, Any] | None:
        """Return the most recent test run for a project, or None."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(TestRun)
                .where(
                    col(TestRun.project_id) == project_id,
                    col(TestRun.org_id) == org_id,
                )
                .order_by(TestRun.created_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            )
            result = await session.execute(stmt)
            run = result.scalars().first()
            if not run:
                return None
            return self._to_dict(run)

    async def get_by_run_uuid(
        self,
        run_uuid: str,
        org_id: str = SENTINEL_ORG_ID,
    ) -> dict[str, Any] | None:
        """Look up a test run by its pipeline UUID."""
        async with AsyncSession(self._engine) as session:
            stmt = select(TestRun).where(
                col(TestRun.run_uuid) == run_uuid,
                col(TestRun.org_id) == org_id,
            )
            result = await session.execute(stmt)
            run = result.scalars().first()
            if not run:
                return None
            return self._to_dict(run)

    async def list_for_project(
        self,
        project_id: int,
        org_id: str = SENTINEL_ORG_ID,
    ) -> list[dict[str, Any]]:
        """Return all test runs for a project, newest first."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(TestRun)
                .where(
                    col(TestRun.project_id) == project_id,
                    col(TestRun.org_id) == org_id,
                )
                .order_by(TestRun.created_at.desc())  # type: ignore[attr-defined]
            )
            result = await session.execute(stmt)
            return [self._to_dict(r) for r in result.scalars().all()]
