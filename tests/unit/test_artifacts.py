from pathlib import Path

import pytest

from breakthevibe.storage.artifacts import ArtifactStore


@pytest.mark.unit
class TestArtifactStore:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> ArtifactStore:
        return ArtifactStore(base_dir=tmp_path)

    def test_creates_project_directory(self, store: ArtifactStore) -> None:
        path = store.get_project_dir("proj-123")
        assert path.exists()
        assert path.is_dir()

    def test_creates_run_directory(self, store: ArtifactStore) -> None:
        path = store.get_run_dir("proj-123", "run-456")
        assert path.exists()
        assert "proj-123" in str(path)
        assert "run-456" in str(path)

    def test_screenshot_path(self, store: ArtifactStore) -> None:
        path = store.screenshot_path("proj-1", "run-1", "step_01")
        assert path.name == "step_01.png"
        assert path.parent.exists()

    def test_video_path(self, store: ArtifactStore) -> None:
        path = store.video_path("proj-1", "run-1", "crawl")
        assert path.name == "crawl.webm"

    def test_diff_path(self, store: ArtifactStore) -> None:
        path = store.diff_path("proj-1", "run-1", "home")
        assert "diffs" in str(path)
        assert path.name == "home.png"

    def test_save_and_load_screenshot(self, store: ArtifactStore) -> None:
        data = b"\x89PNG fake screenshot data"
        path = store.save_screenshot("proj-1", "run-1", "step_01", data)
        assert path.exists()
        assert path.read_bytes() == data

    def test_list_screenshots(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img1")
        store.save_screenshot("proj-1", "run-1", "step_02", b"img2")
        screenshots = store.list_screenshots("proj-1", "run-1")
        assert len(screenshots) == 2

    def test_save_video(self, store: ArtifactStore) -> None:
        data = b"fake video data"
        path = store.save_video("proj-1", "run-1", "crawl", data)
        assert path.exists()
        assert path.read_bytes() == data

    def test_cleanup_run(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img")
        store.save_video("proj-1", "run-1", "crawl", b"vid")
        run_dir = store.get_run_dir("proj-1", "run-1")
        assert any(run_dir.rglob("*"))
        store.cleanup_run("proj-1", "run-1")
        assert not run_dir.exists()

    def test_cleanup_project(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img")
        store.cleanup_project("proj-1")
        project_dir = store._base / "proj-1"
        assert not project_dir.exists()

    def test_get_disk_usage(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"x" * 1000)
        usage = store.get_disk_usage("proj-1")
        assert usage >= 1000
