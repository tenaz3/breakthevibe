"""In-memory project repository (PostgreSQL-backed version in production)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from breakthevibe.config.settings import SENTINEL_ORG_ID

logger = structlog.get_logger(__name__)


class ProjectRepository:
    """In-memory project store. Replaced by SQLModel + PostgreSQL in production."""

    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}

    async def create(
        self,
        name: str,
        url: str,
        rules_yaml: str = "",
        org_id: str = SENTINEL_ORG_ID,
    ) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        project = {
            "id": project_id,
            "org_id": org_id,
            "name": name,
            "url": url,
            "rules_yaml": rules_yaml,
            "created_at": datetime.now(UTC).isoformat(),
            "last_run_at": None,
            "status": "created",
        }
        self._projects[project_id] = project
        logger.info("project_created", id=project_id, name=name, org_id=org_id)
        return project

    async def list_all(self, org_id: str = SENTINEL_ORG_ID) -> list[dict[str, Any]]:
        return [p for p in self._projects.values() if p.get("org_id") == org_id]

    async def get(self, project_id: str, org_id: str = SENTINEL_ORG_ID) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project and project.get("org_id") == org_id:
            return project
        return None

    async def delete(self, project_id: str, org_id: str = SENTINEL_ORG_ID) -> bool:
        project = self._projects.get(project_id)
        if project and project.get("org_id") == org_id:
            del self._projects[project_id]
            logger.info("project_deleted", id=project_id, org_id=org_id)
            return True
        return False

    async def update(
        self, project_id: str, org_id: str = SENTINEL_ORG_ID, **updates: Any
    ) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project and project.get("org_id") == org_id:
            project.update(updates)
            return project
        return None
