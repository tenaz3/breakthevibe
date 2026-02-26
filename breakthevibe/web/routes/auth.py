"""Authentication routes — login, logout, session management."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from breakthevibe.web.auth.session import get_session_auth

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    # If already authenticated, redirect to home
    auth = get_session_auth()
    token = request.cookies.get("session")
    if token and auth.validate_session(token):
        return RedirectResponse(url="/", status_code=302)  # type: ignore[return-value]
    return templates.TemplateResponse("login.html", {"request": request})


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
async def login(body: LoginRequest, response: Response) -> dict[str, str]:
    """Create a session for the user.

    When ADMIN_USERNAME/ADMIN_PASSWORD are set, validates credentials.
    Otherwise falls back to MVP mode (any non-empty credentials accepted).
    """
    if not body.username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password required")

    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if (
        settings.admin_username
        and settings.admin_password
        and (body.username != settings.admin_username or body.password != settings.admin_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    auth = get_session_auth()
    token = auth.create_session(body.username)

    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=86400,
    )
    logger.info("user_logged_in", username=body.username)
    return {"status": "ok", "username": body.username}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Destroy the current session."""
    auth = get_session_auth()
    token = request.cookies.get("session")
    if token:
        auth.destroy_session(token)
    response.delete_cookie("session")
    return {"status": "logged_out"}
