"""Server-Sent Events progress bus for pipeline stage tracking."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import asdict, dataclass


@dataclass
class PipelineProgressEvent:
    """A single pipeline progress event."""

    project_id: str
    stage: str  # PipelineStage.value or "" for terminal events
    status: str  # "started" | "completed" | "failed" | "done"
    error: str = ""
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.monotonic()

    def to_sse(self, event_name: str) -> str:
        """Serialize to SSE wire format."""
        payload = json.dumps(asdict(self))
        return f"event: {event_name}\ndata: {payload}\n\n"


class PipelineProgressBus:
    """In-process fan-out bus for pipeline progress events.

    Designed for single asyncio event loop (single-process uvicorn).
    All callers must be in the same event loop.
    """

    def __init__(self) -> None:
        self._state: dict[str, PipelineProgressEvent] = {}
        self._queues: dict[str, list[asyncio.Queue[PipelineProgressEvent | None]]] = {}

    def notify(self, event: PipelineProgressEvent) -> None:
        """Publish an event to all subscribers for this project.

        Safe to call from a non-async context (put_nowait does not await).
        """
        self._state[event.project_id] = event
        for q in self._queues.get(event.project_id, []):
            q.put_nowait(event)

    def subscribe(self, project_id: str) -> asyncio.Queue[PipelineProgressEvent | None]:
        """Register a new SSE connection queue for this project."""
        q: asyncio.Queue[PipelineProgressEvent | None] = asyncio.Queue()
        self._queues.setdefault(project_id, []).append(q)
        return q

    def unsubscribe(
        self,
        project_id: str,
        q: asyncio.Queue[PipelineProgressEvent | None],
    ) -> None:
        """Remove a disconnected client's queue."""
        queues = self._queues.get(project_id, [])
        with contextlib.suppress(ValueError):
            queues.remove(q)
        if not queues and project_id in self._queues:
            del self._queues[project_id]

    def get_current_state(self, project_id: str) -> PipelineProgressEvent | None:
        """Return the latest known state for a project, or None."""
        return self._state.get(project_id)

    def clear(self, project_id: str) -> None:
        """Remove completed pipeline state."""
        self._state.pop(project_id, None)


# Module-level singleton
progress_bus = PipelineProgressBus()
