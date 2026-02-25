"""Test results API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["results"])


@router.get("/api/runs/{run_id}/results")
async def get_run_results(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "status": "no_data",
        "suites": [],
        "total": 0,
        "passed": 0,
        "failed": 0,
    }
