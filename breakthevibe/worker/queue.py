"""Job queue with SELECT FOR UPDATE SKIP LOCKED for distributed workers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

# Default timeout for stale jobs (15 minutes)
_STALE_JOB_TIMEOUT_MINUTES = 15


class JobQueue:
    """Database-backed job queue using PostgreSQL advisory locks."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def enqueue(
        self,
        org_id: str,
        project_id: str,
        job_type: str = "full",
        url: str = "",
        rules_yaml: str = "",
    ) -> dict[str, Any]:
        """Add a new job to the queue. Returns the created job as a dict (H-4)."""
        import uuid

        job_id = str(uuid.uuid4())
        now = datetime.now(UTC).replace(tzinfo=None)

        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO pipeline_jobs "
                    "(id, org_id, project_id, job_type, status, url, "
                    "rules_yaml, created_at) "
                    "VALUES (:id, :org_id, :project_id, :job_type, "
                    "'pending', :url, :rules_yaml, :created_at)"
                ),
                {
                    "id": job_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "job_type": job_type,
                    "url": url,
                    "rules_yaml": rules_yaml,
                    "created_at": now,
                },
            )

        logger.info("job_enqueued", job_id=job_id, org_id=org_id, project_id=project_id)
        return {
            "id": job_id,
            "org_id": org_id,
            "project_id": project_id,
            "job_type": job_type,
            "status": "pending",
            "url": url,
            "created_at": now.isoformat(),
        }

    async def claim_next(self, max_per_tenant: int = 1) -> dict[str, Any] | None:
        """Claim the next available job using SELECT FOR UPDATE SKIP LOCKED.

        Returns a dict (not ORM object) for the claimed job (H-4), or None.
        Respects per-tenant concurrency limits.
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "WITH eligible AS ("
                    "  SELECT j.id FROM pipeline_jobs j "
                    "  WHERE j.status = 'pending' "
                    "  AND (SELECT COUNT(*) FROM pipeline_jobs r "
                    "       WHERE r.org_id = j.org_id "
                    "       AND r.status = 'running') < :max_per_tenant "
                    "  ORDER BY j.created_at ASC "
                    "  LIMIT 1 "
                    "  FOR UPDATE SKIP LOCKED"
                    ") "
                    "UPDATE pipeline_jobs SET status = 'running', "
                    "started_at = NOW() "
                    "FROM eligible "
                    "WHERE pipeline_jobs.id = eligible.id "
                    "RETURNING pipeline_jobs.id, pipeline_jobs.org_id, "
                    "pipeline_jobs.project_id, pipeline_jobs.job_type, "
                    "pipeline_jobs.url, pipeline_jobs.rules_yaml"
                ),
                {"max_per_tenant": max_per_tenant},
            )
            row = result.fetchone()
            if not row:
                return None

            job = {
                "id": row[0],
                "org_id": row[1],
                "project_id": row[2],
                "job_type": row[3],
                "url": row[4],
                "rules_yaml": row[5],
            }
            logger.info("job_claimed", job_id=job["id"])
            return job

    async def complete(self, job_id: str, error: str | None = None) -> None:
        """Mark a job as completed or failed."""
        status = "failed" if error else "completed"
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE pipeline_jobs SET status = :status, "
                    "finished_at = NOW(), error_message = :error "
                    "WHERE id = :id"
                ),
                {"id": job_id, "status": status, "error": error},
            )
        logger.info("job_completed", job_id=job_id, status=status)

    async def cancel(self, job_id: str, org_id: str) -> bool:
        """Cancel a pending job. Returns True if canceled."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "UPDATE pipeline_jobs SET status = 'canceled', "
                    "finished_at = NOW() "
                    "WHERE id = :id AND org_id = :org_id "
                    "AND status = 'pending'"
                ),
                {"id": job_id, "org_id": org_id},
            )
            return bool(result.rowcount and result.rowcount > 0)

    async def list_jobs(self, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List recent jobs for an org."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id, project_id, job_type, status, url, "
                    "error_message, started_at, finished_at, created_at "
                    "FROM pipeline_jobs "
                    "WHERE org_id = :org_id "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"org_id": org_id, "limit": limit},
            )
            return [
                {
                    "id": row[0],
                    "project_id": row[1],
                    "job_type": row[2],
                    "status": row[3],
                    "url": row[4],
                    "error_message": row[5],
                    "started_at": row[6].isoformat() if row[6] else None,
                    "finished_at": row[7].isoformat() if row[7] else None,
                    "created_at": row[8].isoformat() if row[8] else None,
                }
                for row in result.fetchall()
            ]

    async def get_job(self, job_id: str, org_id: str) -> dict[str, Any] | None:
        """Get a specific job by ID."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id, project_id, job_type, status, url, "
                    "error_message, started_at, finished_at, created_at "
                    "FROM pipeline_jobs "
                    "WHERE id = :id AND org_id = :org_id"
                ),
                {"id": job_id, "org_id": org_id},
            )
            row = result.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "project_id": row[1],
                "job_type": row[2],
                "status": row[3],
                "url": row[4],
                "error_message": row[5],
                "started_at": row[6].isoformat() if row[6] else None,
                "finished_at": row[7].isoformat() if row[7] else None,
                "created_at": row[8].isoformat() if row[8] else None,
            }

    async def recover_stale_jobs(self) -> int:
        """Reset jobs stuck in 'running' state beyond timeout."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "UPDATE pipeline_jobs SET status = 'pending', "
                    "started_at = NULL "
                    "WHERE status = 'running' "
                    "AND started_at < NOW() - INTERVAL ':minutes minutes'"
                ).bindparams(minutes=_STALE_JOB_TIMEOUT_MINUTES),
            )
            count = result.rowcount or 0
            if count:
                logger.warning("stale_jobs_recovered", count=count)
            return count
