"""Visual regression diff engine using Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from PIL import Image

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


@dataclass
class DiffResult:
    """Result of a visual comparison."""

    matches: bool
    diff_percentage: float = 0.0
    diff_image_path: Path | None = None
    size_mismatch: bool = False
    is_new_baseline: bool = False
    total_pixels: int = 0
    different_pixels: int = 0


class VisualDiff:
    """Compares baseline vs current screenshots using pixel comparison."""

    def __init__(self, threshold: float = 0.1) -> None:
        self._threshold = threshold

    def compare(
        self,
        baseline_path: Path,
        current_path: Path,
        output_path: Path | None = None,
    ) -> DiffResult:
        """Compare two images and optionally output a diff image."""
        if not baseline_path.exists():
            logger.info("new_baseline", path=str(current_path))
            return DiffResult(matches=True, is_new_baseline=True)

        baseline = Image.open(baseline_path).convert("RGB")
        current = Image.open(current_path).convert("RGB")

        # Check size mismatch
        if baseline.size != current.size:
            logger.warning(
                "size_mismatch",
                baseline=baseline.size,
                current=current.size,
            )
            return DiffResult(
                matches=False,
                diff_percentage=1.0,
                size_mismatch=True,
            )

        width, height = baseline.size
        total_pixels = width * height
        diff_count = 0

        baseline_pixels = baseline.load()
        current_pixels = current.load()

        # Create diff image if output requested
        diff_img = (
            Image.new("RGB", (width, height), color=(0, 0, 0))
            if output_path
            else None
        )
        diff_pixels = diff_img.load() if diff_img else None

        for y in range(height):
            for x in range(width):
                bp = baseline_pixels[x, y]
                cp = current_pixels[x, y]
                if bp != cp:
                    diff_count += 1
                    if diff_pixels:
                        diff_pixels[x, y] = (255, 0, 255)  # Magenta for diffs
                elif diff_pixels:
                    r, g, b = bp
                    diff_pixels[x, y] = (r // 3, g // 3, b // 3)

        diff_percentage = diff_count / total_pixels if total_pixels > 0 else 0.0
        matches = diff_percentage <= self._threshold

        result_path = None
        if diff_img and output_path:
            diff_img.save(output_path)
            result_path = output_path

        logger.info(
            "visual_diff_complete",
            diff_pct=f"{diff_percentage:.4%}",
            threshold=f"{self._threshold:.4%}",
            matches=matches,
            changed_pixels=diff_count,
            total_pixels=total_pixels,
        )

        return DiffResult(
            matches=matches,
            diff_percentage=diff_percentage,
            diff_image_path=result_path,
            total_pixels=total_pixels,
            different_pixels=diff_count,
        )
