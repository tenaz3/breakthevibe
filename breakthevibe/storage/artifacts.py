"""Local filesystem artifact storage for screenshots, videos, diffs."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


class ArtifactStore:
    """Manages local filesystem storage for binary artifacts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        from pathlib import Path as _Path

        self._base = base_dir or _Path.home() / ".breakthevibe" / "projects"
        self._base.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, project_id: str) -> Path:
        """Get or create project artifact directory."""
        path = self._base / project_id / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_dir(self, project_id: str, run_id: str) -> Path:
        """Get or create run artifact directory."""
        path = self.get_project_dir(project_id) / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_path(self, project_id: str, run_id: str, step_name: str) -> Path:
        """Get path for a screenshot file."""
        screenshots_dir = self.get_run_dir(project_id, run_id) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        return screenshots_dir / f"{step_name}.png"

    def video_path(self, project_id: str, run_id: str, video_name: str) -> Path:
        """Get path for a video file."""
        videos_dir = self.get_run_dir(project_id, run_id) / "videos"
        videos_dir.mkdir(exist_ok=True)
        return videos_dir / f"{video_name}.webm"

    def diff_path(self, project_id: str, run_id: str, diff_name: str) -> Path:
        """Get path for a visual diff image."""
        diffs_dir = self.get_run_dir(project_id, run_id) / "diffs"
        diffs_dir.mkdir(exist_ok=True)
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
        screenshots_dir = self.get_run_dir(project_id, run_id) / "screenshots"
        if not screenshots_dir.exists():
            return []
        return sorted(screenshots_dir.glob("*.png"))

    def cleanup_run(self, project_id: str, run_id: str) -> None:
        """Delete all artifacts for a specific run."""
        run_dir = self._base / project_id / "artifacts" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info("run_artifacts_cleaned", project=project_id, run=run_id)

    def cleanup_project(self, project_id: str) -> None:
        """Delete all artifacts for a project."""
        project_dir = self._base / project_id / "artifacts"
        if project_dir.exists():
            shutil.rmtree(project_dir)
            logger.info("project_artifacts_cleaned", project=project_id)

    def get_disk_usage(self, project_id: str) -> int:
        """Get total disk usage in bytes for a project."""
        project_dir = self._base / project_id / "artifacts"
        if not project_dir.exists():
            return 0
        return sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())
