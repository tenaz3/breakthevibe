"""In-memory project repository (PostgreSQL-backed version in production)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ProjectRepository:
    """In-memory project store. Replaced by SQLModel + PostgreSQL in production."""

    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}

    async def create(self, name: str, url: str, rules_yaml: str = "") -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        project = {
            "id": project_id,
            "name": name,
            "url": url,
            "rules_yaml": rules_yaml,
            "created_at": datetime.now(UTC).isoformat(),
            "last_run_at": None,
            "status": "created",
        }
        self._projects[project_id] = project
        logger.info("project_created", id=project_id, name=name)
        return project

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    async def get(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    async def delete(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            logger.info("project_deleted", id=project_id)
            return True
        return False

    async def update(self, project_id: str, **updates: Any) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project:
            project.update(updates)
            return project
        return None
