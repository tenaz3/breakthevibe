"""Performance measurement utilities."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Generator

logger = structlog.get_logger(__name__)


@contextmanager
def timed(label: str) -> Generator[dict[str, float], None, None]:
    """Context manager that measures elapsed wall-clock time.

    Usage::

        with timed("crawl_page") as t:
            await do_work()
        print(t["elapsed"])  # seconds as float
    """
    result: dict[str, float] = {"elapsed": 0.0}
    start = time.monotonic()
    try:
        yield result
    finally:
        result["elapsed"] = time.monotonic() - start
        logger.debug("timed", label=label, elapsed_seconds=result["elapsed"])


class StopWatch:
    """Simple stopwatch for measuring durations across stages."""

    def __init__(self) -> None:
        self._laps: dict[str, float] = {}
        self._start: float | None = None
        self._current_label: str | None = None

    def start(self, label: str) -> None:
        """Start timing a named section."""
        self._current_label = label
        self._start = time.monotonic()

    def stop(self) -> float:
        """Stop the current section and return its duration."""
        if self._start is None or self._current_label is None:
            return 0.0
        elapsed = time.monotonic() - self._start
        self._laps[self._current_label] = elapsed
        logger.debug("stopwatch_lap", label=self._current_label, elapsed=elapsed)
        self._start = None
        self._current_label = None
        return elapsed

    @property
    def laps(self) -> dict[str, float]:
        """Return all recorded laps."""
        return dict(self._laps)

    @property
    def total(self) -> float:
        """Return total elapsed time across all laps."""
        return sum(self._laps.values())
