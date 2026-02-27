"""Plan tier definitions with concrete limits."""

from __future__ import annotations

from dataclasses import dataclass

UNLIMITED = -1


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Usage limits for a billing plan."""

    max_projects: int
    max_crawls_per_month: int
    max_test_runs_per_month: int
    max_storage_bytes: int
    max_concurrent_pipelines: int


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        max_projects=3,
        max_crawls_per_month=10,
        max_test_runs_per_month=20,
        max_storage_bytes=500 * 1024 * 1024,  # 500 MB
        max_concurrent_pipelines=1,
    ),
    "starter": PlanLimits(
        max_projects=10,
        max_crawls_per_month=50,
        max_test_runs_per_month=100,
        max_storage_bytes=5 * 1024 * 1024 * 1024,  # 5 GB
        max_concurrent_pipelines=2,
    ),
    "pro": PlanLimits(
        max_projects=UNLIMITED,
        max_crawls_per_month=UNLIMITED,
        max_test_runs_per_month=UNLIMITED,
        max_storage_bytes=50 * 1024 * 1024 * 1024,  # 50 GB
        max_concurrent_pipelines=5,
    ),
}


def get_plan_limits(plan: str) -> PlanLimits:
    """Get limits for a plan, defaulting to free tier."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
