# Phase 6: Pipeline Isolation & Job Queue

> **Status**: Not started
> **Depends on**: Phase 1 + Phase 3 (needs org_id + plan limits for concurrency)
> **Estimated scope**: ~5 files created, ~5 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Replace FastAPI `BackgroundTasks` with a persistent PostgreSQL-backed job queue. Enforce per-tenant concurrency limits based on plan tier. Provide job status visibility via API. Ensure jobs survive server restarts.

---

## 2. Why Replace BackgroundTasks?

| Problem | Impact | Solution |
|---|---|---|
| Jobs lost on restart | Users must manually re-trigger | Persistent DB rows |
| No concurrency control | One tenant hogs all resources | Per-tenant limits from plan |
| No retry on crash | Silent failures | Auto-retry with attempt tracking |
| In-process execution | Blocks event loop | Separate worker process |
| No visibility | Users can't see queue status | Job status API |

---

## 3. PipelineJob Model

**Add to: `breakthevibe/models/database.py`**

```python
class PipelineJob(SQLModel, table=True):
    """Persistent pipeline job queue entry."""

    __tablename__ = "pipeline_jobs"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        sa_column=Column(sa.String(36), primary_key=True),
    )
    org_id: str = Field(foreign_key="organizations.id", index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending", index=True)
    # Status values: pending | running | completed | failed | canceled
    url: str
    rules_yaml: str = Field(default="")
    priority: int = Field(default=0)          # Higher = more urgent
    max_retries: int = Field(default=3)
    attempt: int = Field(default=0)
    worker_id: str | None = None              # Claim token
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    result_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

---

## 4. Job Queue Implementation

**Create: `breakthevibe/worker/__init__.py`** (empty)

**Create: `breakthevibe/worker/queue.py`**

```python
"""PostgreSQL-backed job queue with per-tenant concurrency limits."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.billing.plans import get_plan_limit
from breakthevibe.models.database import PipelineJob, Subscription
from breakthevibe.storage.database import get_engine

logger = structlog.get_logger(__name__)


class JobQueue:
    """Manages pipeline jobs in PostgreSQL.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent claiming.
    Enforces per-tenant concurrency limits based on plan tier.
    """

    async def enqueue(
        self,
        org_id: str,
        project_id: int,
        url: str,
        rules_yaml: str = "",
        priority: int = 0,
    ) -> PipelineJob:
        """Create a new pipeline job."""
        async with AsyncSession(get_engine()) as session:
            job = PipelineJob(
                org_id=org_id,
                project_id=project_id,
                url=url,
                rules_yaml=rules_yaml,
                priority=priority,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info("job_enqueued", job_id=job.id, org_id=org_id,
                        project_id=project_id)
            return job

    async def claim_next(self, worker_id: str) -> PipelineJob | None:
        """Claim the next available job, respecting per-tenant concurrency limits.

        Uses FOR UPDATE SKIP LOCKED to prevent race conditions between workers.
        """
        async with AsyncSession(get_engine()) as session:
            # Raw SQL for the complex claiming query
            result = await session.execute(
                text("""
                    WITH eligible AS (
                        SELECT j.id
                        FROM pipeline_jobs j
                        JOIN organizations o ON j.org_id = o.id
                        LEFT JOIN subscriptions s ON s.org_id = j.org_id
                            AND s.status = 'active'
                        WHERE j.status = 'pending'
                        AND (
                            SELECT COUNT(*)
                            FROM pipeline_jobs running
                            WHERE running.org_id = j.org_id
                            AND running.status = 'running'
                        ) < CASE COALESCE(s.plan, 'free')
                            WHEN 'free' THEN 1
                            WHEN 'starter' THEN 3
                            WHEN 'pro' THEN 10
                            ELSE 1
                          END
                        ORDER BY j.priority DESC, j.created_at ASC
                        LIMIT 1
                        FOR UPDATE OF j SKIP LOCKED
                    )
                    UPDATE pipeline_jobs
                    SET status = 'running',
                        worker_id = :worker_id,
                        started_at = :now,
                        attempt = attempt + 1,
                        updated_at = :now
                    WHERE id = (SELECT id FROM eligible)
                    RETURNING *
                """),
                {
                    "worker_id": worker_id,
                    "now": datetime.now(UTC),
                },
            )
            row = result.first()
            if not row:
                return None

            await session.commit()

            # Convert row to PipelineJob
            job = await session.get(PipelineJob, row.id)
            logger.info("job_claimed", job_id=job.id, worker_id=worker_id,
                        org_id=job.org_id)
            return job

    async def complete(self, job_id: str, result_data: dict[str, Any]) -> None:
        """Mark a job as completed with result data."""
        async with AsyncSession(get_engine()) as session:
            job = await session.get(PipelineJob, job_id)
            if job:
                job.status = "completed"
                job.finished_at = datetime.now(UTC)
                job.result_json = json.dumps(result_data)
                job.updated_at = datetime.now(UTC)
                session.add(job)
                await session.commit()
                logger.info("job_completed", job_id=job_id)

    async def fail(self, job_id: str, error: str) -> None:
        """Mark a job as failed. If retries remain, reset to pending."""
        async with AsyncSession(get_engine()) as session:
            job = await session.get(PipelineJob, job_id)
            if job:
                if job.attempt < job.max_retries:
                    job.status = "pending"  # Will be retried
                    job.worker_id = None
                    logger.info("job_retry_scheduled", job_id=job_id,
                                attempt=job.attempt, max=job.max_retries)
                else:
                    job.status = "failed"
                    job.finished_at = datetime.now(UTC)
                    logger.warning("job_failed_permanently", job_id=job_id,
                                   error=error)
                job.error_message = error
                job.updated_at = datetime.now(UTC)
                session.add(job)
                await session.commit()

    async def cancel(self, job_id: str, org_id: str) -> bool:
        """Cancel a pending job. Returns True if canceled."""
        async with AsyncSession(get_engine()) as session:
            stmt = select(PipelineJob).where(
                PipelineJob.id == job_id,
                PipelineJob.org_id == org_id,
                PipelineJob.status == "pending",
            )
            job = (await session.execute(stmt)).scalars().first()
            if not job:
                return False
            job.status = "canceled"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            await session.commit()
            logger.info("job_canceled", job_id=job_id)
            return True

    async def list_jobs(
        self, org_id: str, status: str | None = None, limit: int = 50
    ) -> list[PipelineJob]:
        """List jobs for an organization."""
        async with AsyncSession(get_engine()) as session:
            stmt = (
                select(PipelineJob)
                .where(PipelineJob.org_id == org_id)
                .order_by(PipelineJob.created_at.desc())
                .limit(limit)
            )
            if status:
                stmt = stmt.where(PipelineJob.status == status)
            results = (await session.execute(stmt)).scalars().all()
            return list(results)

    async def get_job(self, job_id: str, org_id: str) -> PipelineJob | None:
        """Get a single job (tenant-scoped)."""
        async with AsyncSession(get_engine()) as session:
            stmt = select(PipelineJob).where(
                PipelineJob.id == job_id,
                PipelineJob.org_id == org_id,
            )
            return (await session.execute(stmt)).scalars().first()

    async def reclaim_stale(self, stale_seconds: int = 600) -> int:
        """Reset jobs stuck in 'running' for too long (worker crash recovery)."""
        async with AsyncSession(get_engine()) as session:
            cutoff = datetime.now(UTC).timestamp() - stale_seconds
            result = await session.execute(
                text("""
                    UPDATE pipeline_jobs
                    SET status = 'pending', worker_id = NULL, updated_at = NOW()
                    WHERE status = 'running'
                    AND started_at < :cutoff
                """),
                {"cutoff": datetime.fromtimestamp(cutoff, tz=UTC)},
            )
            count = result.rowcount
            await session.commit()
            if count:
                logger.warning("stale_jobs_reclaimed", count=count)
            return count
```

---

## 5. Job Worker

**Create: `breakthevibe/worker/runner.py`**

```python
"""Job worker — polls the queue and executes pipeline jobs."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from breakthevibe.worker.queue import JobQueue

logger = structlog.get_logger(__name__)


class JobWorker:
    """Polls the job queue and executes pipeline jobs."""

    def __init__(
        self,
        queue: JobQueue,
        poll_interval: float = 2.0,
        stale_check_interval: float = 60.0,
    ) -> None:
        self._queue = queue
        self._poll_interval = poll_interval
        self._stale_check_interval = stale_check_interval
        self._worker_id = str(uuid.uuid4())
        self._running = False

    async def run_forever(self) -> None:
        """Main loop: claim and execute jobs."""
        self._running = True
        logger.info("worker_started", worker_id=self._worker_id)

        stale_check_counter = 0.0

        while self._running:
            job = await self._queue.claim_next(self._worker_id)
            if job:
                await self._execute(job)
                stale_check_counter = 0.0
            else:
                await asyncio.sleep(self._poll_interval)
                stale_check_counter += self._poll_interval

            # Periodically reclaim stale jobs
            if stale_check_counter >= self._stale_check_interval:
                await self._queue.reclaim_stale()
                stale_check_counter = 0.0

    async def _execute(self, job: Any) -> None:
        """Run a single pipeline job."""
        from breakthevibe.web.pipeline import build_pipeline

        logger.info(
            "job_executing",
            job_id=job.id,
            org_id=job.org_id,
            project_id=job.project_id,
        )
        try:
            orchestrator = build_pipeline(
                project_id=str(job.project_id),
                url=job.url,
                rules_yaml=job.rules_yaml,
            )
            result = await orchestrator.run(
                project_id=str(job.project_id),
                url=job.url,
                rules_yaml=job.rules_yaml,
            )

            result_data = {
                "run_id": result.run_id,
                "success": result.success,
                "completed_stages": [s.value for s in result.completed_stages],
                "failed_stage": result.failed_stage.value if result.failed_stage else None,
                "error_message": result.error_message,
                "duration_seconds": result.duration_seconds,
            }
            await self._queue.complete(job.id, result_data)

        except Exception as e:
            logger.error("job_execution_error", job_id=job.id, error=str(e))
            await self._queue.fail(job.id, str(e))

    def stop(self) -> None:
        self._running = False
        logger.info("worker_stopping", worker_id=self._worker_id)
```

**Worker entry point** (add to `breakthevibe/worker/__init__.py` or as CLI command):

```python
# breakthevibe/worker/cli.py
"""Worker CLI entry point."""

import asyncio
from breakthevibe.worker.queue import JobQueue
from breakthevibe.worker.runner import JobWorker


def run_worker() -> None:
    queue = JobQueue()
    worker = JobWorker(queue)
    asyncio.run(worker.run_forever())
```

Add to `pyproject.toml`:
```toml
[project.scripts]
breakthevibe = "breakthevibe.main:cli"
breakthevibe-worker = "breakthevibe.worker.cli:run_worker"
```

---

## 6. Job Status API

**Create: `breakthevibe/web/routes/jobs.py`**

```python
"""Pipeline job status API routes."""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from breakthevibe.web.auth.rbac import require_member, require_viewer
from breakthevibe.web.tenant_context import TenantContext
from breakthevibe.worker.queue import JobQueue

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_queue = JobQueue()


@router.get("")
async def list_jobs(
    tenant: TenantContext = Depends(require_viewer),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """List pipeline jobs for this organization."""
    jobs = await _queue.list_jobs(tenant.org_id, status=status, limit=limit)
    return [
        {
            "id": j.id,
            "project_id": j.project_id,
            "status": j.status,
            "url": j.url,
            "attempt": j.attempt,
            "max_retries": j.max_retries,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat(),
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    tenant: TenantContext = Depends(require_viewer),
) -> dict[str, Any]:
    """Get a single job's status and result."""
    job = await _queue.get_job(job_id, tenant.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "url": job.url,
        "attempt": job.attempt,
        "max_retries": job.max_retries,
        "error_message": job.error_message,
        "result": json.loads(job.result_json) if job.result_json else None,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.delete("/{job_id}", status_code=204)
async def cancel_job(
    job_id: str,
    tenant: TenantContext = Depends(require_member),
) -> None:
    """Cancel a pending job."""
    canceled = await _queue.cancel(job_id, tenant.org_id)
    if not canceled:
        raise HTTPException(
            status_code=404, detail="Job not found or not in pending state"
        )
```

---

## 7. Route Changes (Replace BackgroundTasks)

### crawl.py

```python
# BEFORE:
background_tasks.add_task(run_pipeline, project_id=project_id, ...)
return {"status": "accepted", "project_id": project_id}

# AFTER:
from breakthevibe.worker.queue import JobQueue
_queue = JobQueue()

job = await _queue.enqueue(
    org_id=tenant.org_id,
    project_id=int(project_id),
    url=project["url"],
    rules_yaml=project.get("rules_yaml", ""),
)
return {"status": "accepted", "project_id": project_id, "job_id": job.id}
```

Same pattern for `tests.py` (`trigger_generate`, `trigger_run`).

---

## 8. Docker Compose — Worker Service

**Add to `docker-compose.yml`:**

```yaml
  worker:
    build: .
    command: ["uv", "run", "breakthevibe-worker"]
    environment:
      DATABASE_URL: postgresql+asyncpg://breakthevibe:breakthevibe@db:5432/breakthevibe
      USE_DATABASE: "true"
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
    depends_on:
      db:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    volumes:
      - artifact_data:/data/artifacts
```

---

## 9. Alembic Migration

```python
"""add pipeline_jobs table"""

def upgrade() -> None:
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("rules_yaml", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_jobs_org_id", "pipeline_jobs", ["org_id"])
    op.create_index("ix_pipeline_jobs_project_id", "pipeline_jobs", ["project_id"])
    op.create_index("ix_pipeline_jobs_status", "pipeline_jobs", ["status"])
    # Composite index for the claim query
    op.create_index(
        "ix_pipeline_jobs_claim",
        "pipeline_jobs",
        ["status", "priority", "created_at"],
    )
```

---

## 10. Verification Checklist

- [ ] Enqueue creates a pending job in DB
- [ ] Worker claims and executes the job
- [ ] Completed job has result_json populated
- [ ] Failed job retries up to max_retries then stays failed
- [ ] Two workers don't claim the same job (SKIP LOCKED)
- [ ] Free-tier tenant limited to 1 concurrent pipeline
- [ ] Pro-tier tenant can run up to 10 concurrently
- [ ] `GET /api/jobs` lists jobs for current org only
- [ ] `DELETE /api/jobs/{id}` cancels pending jobs
- [ ] Worker restart reclaims stale running jobs
- [ ] `breakthevibe-worker` CLI entry point works

---

## 11. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/worker/__init__.py` |
| CREATE | `breakthevibe/worker/queue.py` (~180 lines) |
| CREATE | `breakthevibe/worker/runner.py` (~80 lines) |
| CREATE | `breakthevibe/worker/cli.py` (~15 lines) |
| CREATE | `breakthevibe/web/routes/jobs.py` (~80 lines) |
| CREATE | migration: `add_pipeline_jobs_table.py` |
| MODIFY | `breakthevibe/models/database.py` (PipelineJob model) |
| MODIFY | `breakthevibe/web/routes/crawl.py` (enqueue instead of BackgroundTask) |
| MODIFY | `breakthevibe/web/routes/tests.py` (same) |
| MODIFY | `breakthevibe/web/app.py` (register jobs router) |
| MODIFY | `pyproject.toml` (worker CLI entry point) |
| MODIFY | `docker-compose.yml` (worker service) |
