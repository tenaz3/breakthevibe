from pathlib import Path

import pytest
from PIL import Image

from breakthevibe.reporter.diff import DiffResult, VisualDiff


@pytest.mark.unit
class TestVisualDiff:
    @pytest.fixture()
    def differ(self) -> VisualDiff:
        return VisualDiff(threshold=0.1)

    @pytest.fixture()
    def identical_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two identical test images."""
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        img.save(baseline)
        img.save(current)
        return baseline, current

    @pytest.fixture()
    def different_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two different test images."""
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (100, 100), color=(0, 0, 255))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        return baseline, current

    @pytest.fixture()
    def slightly_different_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two images with minor differences."""
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        for x in range(5):
            for y in range(5):
                current_img.putpixel((x, y), (254, 1, 1))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        return baseline, current

    def test_identical_images_pass(
        self,
        differ: VisualDiff,
        identical_images: tuple[Path, Path],
    ) -> None:
        baseline, current = identical_images
        result = differ.compare(baseline, current)
        assert isinstance(result, DiffResult)
        assert result.matches is True
        assert result.diff_percentage == 0.0

    def test_different_images_fail(
        self,
        differ: VisualDiff,
        different_images: tuple[Path, Path],
    ) -> None:
        baseline, current = different_images
        result = differ.compare(baseline, current)
        assert result.matches is False
        assert result.diff_percentage > 0.1

    def test_generates_diff_image(
        self,
        differ: VisualDiff,
        different_images: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        baseline, current = different_images
        diff_path = tmp_path / "diff.png"
        result = differ.compare(baseline, current, output_path=diff_path)
        assert diff_path.exists()
        assert result.diff_image_path == diff_path

    def test_slight_diff_below_threshold(
        self,
        differ: VisualDiff,
        slightly_different_images: tuple[Path, Path],
    ) -> None:
        baseline, current = slightly_different_images
        result = differ.compare(baseline, current)
        # 25 pixels out of 10000 = 0.25% which is below 10% threshold
        assert result.matches is True

    def test_different_size_images(self, differ: VisualDiff, tmp_path: Path) -> None:
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        result = differ.compare(baseline, current)
        assert result.matches is False
        assert result.size_mismatch is True

    def test_missing_baseline_creates_new(self, differ: VisualDiff, tmp_path: Path) -> None:
        baseline = tmp_path / "nonexistent.png"
        current_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current = tmp_path / "current.png"
        current_img.save(current)
        result = differ.compare(baseline, current)
        assert result.is_new_baseline is True
        assert result.matches is True

    def test_custom_threshold(self, tmp_path: Path) -> None:
        strict_differ = VisualDiff(threshold=0.001)
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        for x in range(2):
            for y in range(2):
                img2.putpixel((x, y), (254, 1, 1))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        img1.save(baseline)
        img2.save(current)
        result = strict_differ.compare(baseline, current)
        assert result.diff_percentage < 0.01
