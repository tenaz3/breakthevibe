"""Job worker polling loop for pipeline execution."""

from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from breakthevibe.worker.queue import JobQueue

logger = structlog.get_logger(__name__)


class JobWorker:
    """Polls the job queue and executes pipeline jobs.

    Handles SIGTERM/SIGINT for graceful shutdown (M-4).
    """

    def __init__(
        self,
        queue: JobQueue,
        poll_interval: float = 2.0,
        max_per_tenant: int = 1,
    ) -> None:
        self._queue = queue
        self._poll_interval = poll_interval
        self._max_per_tenant = max_per_tenant
        self._running = True

    async def run(self) -> None:
        """Main polling loop."""
        loop = asyncio.get_running_loop()

        # M-4: Graceful shutdown on SIGTERM/SIGINT
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        logger.info("worker_started", poll_interval=self._poll_interval)

        while self._running:
            try:
                # Recover stale jobs periodically
                await self._queue.recover_stale_jobs()

                job = await self._queue.claim_next(max_per_tenant=self._max_per_tenant)
                if job:
                    await self._execute(job)
                else:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("worker_poll_error")
                await asyncio.sleep(self._poll_interval)

        logger.info("worker_stopped")

    async def _execute(self, job: dict[str, Any]) -> None:
        """Execute a single pipeline job."""
        job_id = job["id"]
        logger.info(
            "job_executing",
            job_id=job_id,
            project_id=job["project_id"],
            org_id=job["org_id"],
        )

        try:
            from breakthevibe.web.dependencies import run_pipeline

            await run_pipeline(
                project_id=job["project_id"],
                url=job["url"],
                rules_yaml=job.get("rules_yaml", ""),
                org_id=job["org_id"],
            )
            await self._queue.complete(job_id)
        except Exception as exc:
            logger.error("job_failed", job_id=job_id, error=str(exc))
            await self._queue.complete(job_id, error=str(exc))

    def _shutdown(self) -> None:
        """Signal handler for graceful shutdown."""
        logger.info("worker_shutdown_requested")
        self._running = False
