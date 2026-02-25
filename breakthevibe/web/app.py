"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from breakthevibe.web.middleware import RequestIDMiddleware
from breakthevibe.web.routes.crawl import router as crawl_router
from breakthevibe.web.routes.pages import router as pages_router
from breakthevibe.web.routes.projects import router as projects_router
from breakthevibe.web.routes.results import router as results_router
from breakthevibe.web.routes.settings import router as settings_router
from breakthevibe.web.routes.tests import router as tests_router

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BreakTheVibe",
        description="AI-powered QA automation platform",
        version="0.1.0",
    )

    # Middleware (order matters — last added runs first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Routers
    app.include_router(projects_router)
    app.include_router(crawl_router)
    app.include_router(tests_router)
    app.include_router(results_router)
    app.include_router(pages_router)
    app.include_router(settings_router)

    # Health check
    @app.get("/api/health")
    async def health_check() -> dict:
        return {"status": "healthy", "version": "0.1.0"}

    # Mount static files if directory exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    logger.info("app_created")
    return app
