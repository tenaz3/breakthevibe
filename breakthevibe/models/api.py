"""API request/response schemas for FastAPI endpoints."""

from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    url: str
    config_yaml: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    url: str
    created_at: datetime


class CrawlRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None


class TestCaseResponse(BaseModel):
    id: int
    name: str
    category: str
    route_path: str


class TestRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    total: int
    passed: int
    failed: int
    healed: int


class TestResultResponse(BaseModel):
    id: int
    test_case_id: int
    status: str
    duration_ms: int | None
    error_message: str | None
