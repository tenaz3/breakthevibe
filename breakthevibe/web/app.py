"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from breakthevibe.config.logging import setup_logging
from breakthevibe.config.settings import get_settings
from breakthevibe.web.auth.session import require_auth
from breakthevibe.web.middleware import RateLimitMiddleware, RequestIDMiddleware
from breakthevibe.web.routes.audit import router as audit_router
from breakthevibe.web.routes.auth import router as auth_router
from breakthevibe.web.routes.crawl import router as crawl_router
from breakthevibe.web.routes.jobs import router as jobs_router
from breakthevibe.web.routes.pages import router as pages_router
from breakthevibe.web.routes.projects import router as projects_router
from breakthevibe.web.routes.results import router as results_router
from breakthevibe.web.routes.settings import router as settings_router
from breakthevibe.web.routes.sse import router as sse_router
from breakthevibe.web.routes.tests import router as tests_router
from breakthevibe.web.security_headers import SecurityHeadersMiddleware

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=not settings.debug)

    app = FastAPI(
        title="BreakTheVibe",
        description="AI-powered QA automation platform",
        version="0.1.0",
    )

    # Redirect 401s to /login for browser page requests; return JSON for API
    @app.exception_handler(401)
    async def auth_redirect_handler(
        request: Request, exc: HTTPException
    ) -> RedirectResponse | JSONResponse:
        if not request.url.path.startswith("/api/"):
            next_url = quote(str(request.url.path), safe="/")
            return RedirectResponse(url=f"/login?next={next_url}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # Middleware (order matters — last added runs first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
    app.add_middleware(RequestIDMiddleware)

    # Public routes (no auth required)
    app.include_router(auth_router)

    # Clerk webhooks (public, signature-verified internally)
    if settings.auth_mode == "clerk":
        from breakthevibe.web.auth.webhook import router as webhook_router

        app.include_router(webhook_router)

    # Health check (public)
    @app.get("/api/health")
    async def health_check() -> dict[str, object]:
        from breakthevibe.web.health import check_health

        return await check_health()

    # Protected routes (require session auth — API returns 401, pages redirect to /login)
    protected = [
        projects_router,
        crawl_router,
        tests_router,
        results_router,
        settings_router,
        jobs_router,
        audit_router,
        sse_router,
    ]
    for router in protected:
        app.include_router(router, dependencies=[Depends(require_auth)])

    # Page routes (also protected)
    app.include_router(pages_router, dependencies=[Depends(require_auth)])

    # Mount static files if directory exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    logger.info("app_created")
    return app
