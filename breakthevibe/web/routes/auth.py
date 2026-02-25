"""Authentication routes — login, logout, session management."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from breakthevibe.web.auth.session import get_session_auth

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
async def login(body: LoginRequest, response: Response) -> dict:
    """Create a session for the user.

    In MVP, accepts any non-empty username/password.
    Replace with real credential validation in production.
    """
    if not body.username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password required")

    auth = get_session_auth()
    token = auth.create_session(body.username)

    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    logger.info("user_logged_in", username=body.username)
    return {"status": "ok", "username": body.username}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict:
    """Destroy the current session."""
    auth = get_session_auth()
    token = request.cookies.get("session")
    if token:
        auth.destroy_session(token)
    response.delete_cookie("session")
    return {"status": "logged_out"}
