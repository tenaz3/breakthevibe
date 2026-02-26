"""SSE endpoint for real-time pipeline progress streaming."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from breakthevibe.web.sse import PipelineProgressEvent, progress_bus

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["sse"])

_HEARTBEAT_INTERVAL = 15.0  # seconds


@router.get("/api/projects/{project_id}/progress")
async def pipeline_progress_stream(
    project_id: str,
    request: Request,
) -> StreamingResponse:
    """Stream pipeline stage progress as Server-Sent Events."""

    async def event_generator() -> AsyncGenerator[str, None]:
        q = progress_bus.subscribe(project_id)
        logger.info("sse_client_connected", project_id=project_id)

        try:
            # Backfill: if a pipeline is already running, send current state
            current = progress_bus.get_current_state(project_id)
            if current is not None:
                if current.status in ("done", "failed"):
                    yield current.to_sse(current.status)
                    return
                yield current.to_sse("connected")

            while True:
                if await request.is_disconnected():
                    break

                try:
                    event: PipelineProgressEvent | None = await asyncio.wait_for(
                        q.get(), timeout=_HEARTBEAT_INTERVAL
                    )
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event is None:
                    break

                if event.status == "done":
                    event_name = "done"
                elif event.status == "failed":
                    event_name = "failed"
                else:
                    event_name = "stage"

                yield event.to_sse(event_name)

                if event_name in ("done", "failed"):
                    break

        finally:
            progress_bus.unsubscribe(project_id, q)
            logger.info("sse_stream_closed", project_id=project_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
