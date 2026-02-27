"""CLI entry point for the pipeline job worker."""

from __future__ import annotations

import asyncio

import structlog

from breakthevibe.config.logging import setup_logging
from breakthevibe.storage.database import get_engine
from breakthevibe.worker.queue import JobQueue
from breakthevibe.worker.runner import JobWorker

logger = structlog.get_logger(__name__)


def main() -> None:
    """Start the pipeline job worker."""
    setup_logging(log_level="INFO", json_output=True)
    engine = get_engine()
    queue = JobQueue(engine)
    worker = JobWorker(queue)
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
