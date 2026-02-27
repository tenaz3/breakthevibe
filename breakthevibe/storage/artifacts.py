"""Tenant-aware artifact storage for screenshots, videos, diffs.

Wraps an ObjectStore with tenant-prefixed keys and provides both
sync (local path-based) and async (ObjectStore-based) APIs.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from breakthevibe.config.settings import SENTINEL_ORG_ID

if TYPE_CHECKING:
    from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


def _tenant_prefix(org_id: str, project_id: str) -> str:
    """Build tenant-namespaced key prefix."""
    return f"tenants/{org_id}/projects/{project_id}"


class ArtifactStore:
    """Manages artifact storage with tenant isolation.

    In local mode, operates directly on filesystem paths.
    When an ObjectStore is provided, delegates to it for storage operations.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        store: ObjectStore | None = None,
        org_id: str = SENTINEL_ORG_ID,
    ) -> None:
        self._base = (base_dir or Path.home() / ".breakthevibe" / "projects").resolve()
        self._base.mkdir(parents=True, exist_ok=True)
        self._store = store
        self._org_id = org_id

    def _safe_path(self, *parts: str) -> Path:
        """Resolve path with traversal protection (C-7)."""
        path = (self._base / Path(*parts)).resolve()
        if not str(path).startswith(str(self._base)):
            msg = f"Path traversal detected: {'/'.join(parts)}"
            raise ValueError(msg)
        return path

    def get_project_dir(self, project_id: str) -> Path:
        """Get or create project artifact directory."""
        path = self._safe_path(project_id, "artifacts")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_dir(self, project_id: str, run_id: str) -> Path:
        """Get or create run artifact directory."""
        path = self._safe_path(project_id, "artifacts", run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_path(self, project_id: str, run_id: str, step_name: str) -> Path:
        """Get path for a screenshot file."""
        screenshots_dir = self._safe_path(project_id, "artifacts", run_id, "screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return screenshots_dir / f"{step_name}.png"

    def video_path(self, project_id: str, run_id: str, video_name: str) -> Path:
        """Get path for a video file."""
        videos_dir = self._safe_path(project_id, "artifacts", run_id, "videos")
        videos_dir.mkdir(parents=True, exist_ok=True)
        return videos_dir / f"{video_name}.webm"

    def diff_path(self, project_id: str, run_id: str, diff_name: str) -> Path:
        """Get path for a visual diff image."""
        diffs_dir = self._safe_path(project_id, "artifacts", run_id, "diffs")
        diffs_dir.mkdir(parents=True, exist_ok=True)
        return diffs_dir / f"{diff_name}.png"

    def save_screenshot(self, project_id: str, run_id: str, step_name: str, data: bytes) -> Path:
        """Save screenshot data to file."""
        path = self.screenshot_path(project_id, run_id, step_name)
        path.write_bytes(data)
        logger.debug("screenshot_saved", path=str(path), size=len(data))
        return path

    def save_video(self, project_id: str, run_id: str, video_name: str, data: bytes) -> Path:
        """Save video data to file."""
        path = self.video_path(project_id, run_id, video_name)
        path.write_bytes(data)
        logger.debug("video_saved", path=str(path), size=len(data))
        return path

    def list_screenshots(self, project_id: str, run_id: str) -> list[Path]:
        """List all screenshots for a run."""
        screenshots_dir = self._safe_path(project_id, "artifacts", run_id, "screenshots")
        if not screenshots_dir.exists():
            return []
        return sorted(screenshots_dir.glob("*.png"))

    def cleanup_run(self, project_id: str, run_id: str) -> None:
        """Delete all artifacts for a specific run."""
        run_dir = self._safe_path(project_id, "artifacts", run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info("run_artifacts_cleaned", project=project_id, run=run_id)

    def cleanup_project(self, project_id: str) -> None:
        """Delete all artifacts for a project."""
        project_dir = self._safe_path(project_id, "artifacts")
        if project_dir.exists():
            shutil.rmtree(project_dir)
            logger.info("project_artifacts_cleaned", project=project_id)

    def get_disk_usage(self, project_id: str) -> int:
        """Get total disk usage in bytes for a project."""
        project_dir = self._safe_path(project_id, "artifacts")
        if not project_dir.exists():
            return 0
        return sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())

    # --- Async ObjectStore-backed methods ---

    async def async_put(self, project_id: str, key: str, data: bytes) -> str:
        """Store data via ObjectStore with tenant-prefixed key.

        Returns the full key used for storage.
        """
        full_key = f"{_tenant_prefix(self._org_id, project_id)}/{key}"
        if self._store:
            await self._store.put(full_key, data)
        else:
            path = self._safe_path(project_id, *key.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return full_key

    async def async_get(self, project_id: str, key: str) -> bytes | None:
        """Retrieve data via ObjectStore."""
        full_key = f"{_tenant_prefix(self._org_id, project_id)}/{key}"
        if self._store:
            return await self._store.get(full_key)
        path = self._safe_path(project_id, *key.split("/"))
        if path.exists():
            return path.read_bytes()
        return None

    async def async_delete(self, project_id: str, key: str) -> None:
        """Delete data via ObjectStore."""
        full_key = f"{_tenant_prefix(self._org_id, project_id)}/{key}"
        if self._store:
            await self._store.delete(full_key)
        else:
            path = self._safe_path(project_id, *key.split("/"))
            if path.exists():
                path.unlink()

    async def async_get_usage(self, project_id: str) -> int:
        """Get storage usage via ObjectStore."""
        prefix = _tenant_prefix(self._org_id, project_id)
        if self._store:
            return await self._store.get_usage_bytes(prefix)
        return self.get_disk_usage(project_id)
