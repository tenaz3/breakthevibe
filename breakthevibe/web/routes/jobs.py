"""Pipeline job queue API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from breakthevibe.web.auth.rbac import get_tenant

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext
    from breakthevibe.worker.queue import JobQueue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_queue() -> JobQueue:
    """Get the job queue instance."""
    from breakthevibe.storage.database import get_engine
    from breakthevibe.worker.queue import JobQueue as _JobQueue

    return _JobQueue(get_engine())


@router.get("")
async def list_jobs(
    tenant: TenantContext = Depends(get_tenant),
) -> list[dict[str, Any]]:
    queue = _get_queue()
    return await queue.list_jobs(org_id=tenant.org_id)


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    queue = _get_queue()
    job = await queue.get_job(job_id, org_id=tenant.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    queue = _get_queue()
    canceled = await queue.cancel(job_id, org_id=tenant.org_id)
    if not canceled:
        raise HTTPException(status_code=404, detail="Job not found or not cancelable")
    return {"status": "canceled"}
