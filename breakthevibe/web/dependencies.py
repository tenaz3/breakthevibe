"""FastAPI dependency injection."""

from __future__ import annotations

from breakthevibe.storage.repositories.projects import ProjectRepository

# Shared in-memory repo (replaced by DB session DI in production)
project_repo = ProjectRepository()
