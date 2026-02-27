"""Authentication routes — passkey WebAuthn, password login, logout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from breakthevibe.audit.logger import audit
from breakthevibe.config.settings import SENTINEL_ORG_ID, get_settings
from breakthevibe.web.auth.session import get_session_auth

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the login page (password or passkey depending on auth_mode)."""
    auth = get_session_auth()
    token = request.cookies.get("session")
    if token and auth.validate_session(token):
        return RedirectResponse(url="/", status_code=302)  # type: ignore[return-value]

    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "login.html",
        {"auth_mode": settings.auth_mode},
    )


# ---------------------------------------------------------------------------
# Registration page (passkey bootstrap — first user)
# ---------------------------------------------------------------------------


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Render the passkey registration page.

    Only accessible when auth_mode == "passkey" and no users have credentials yet.
    """
    settings = get_settings()
    if settings.auth_mode != "passkey":
        return RedirectResponse(url="/login", status_code=302)  # type: ignore[return-value]

    return templates.TemplateResponse(request, "register.html")


# ---------------------------------------------------------------------------
# Password login (auth_mode == "single")
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    """Create a session via username/password (single mode only)."""
    settings = get_settings()
    if settings.auth_mode == "passkey":
        raise HTTPException(status_code=400, detail="Use passkey authentication")

    if not body.username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password required")

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
    await audit(
        org_id=SENTINEL_ORG_ID,
        user_id=body.username,
        action="auth.login",
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("user_logged_in", username=body.username)
    return {"status": "ok", "username": body.username}


# ---------------------------------------------------------------------------
# Passkey WebAuthn endpoints
# ---------------------------------------------------------------------------


class PasskeyRegisterBeginRequest(BaseModel):
    email: str


@router.post("/api/auth/passkey/register/begin")
async def passkey_register_begin(
    body: PasskeyRegisterBeginRequest,
) -> dict[str, Any]:
    """Begin passkey registration ceremony."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        raise HTTPException(status_code=400, detail="Passkey auth not enabled")

    from breakthevibe.web.dependencies import passkey_service, user_repo

    if passkey_service is None or user_repo is None:
        raise HTTPException(status_code=500, detail="Passkey service not configured")

    # Check if this is a bootstrap (no credentials exist yet)
    has_credentials = await passkey_service.has_any_credentials()
    if has_credentials:
        raise HTTPException(
            status_code=403,
            detail="Registration is closed. Contact an admin for an invite.",
        )

    # Look up or create user
    user = await user_repo.get_by_email(body.email)
    webauthn_user_id: bytes | None = None
    if user:
        user_id = user.id
        webauthn_user_id = await passkey_service.get_webauthn_user_id(user.id)
    else:
        has_users = await user_repo.has_any()
        role = "admin" if not has_users else "member"
        user = await user_repo.create(email=body.email, role=role)
        user_id = user.id

    result = await passkey_service.begin_registration(
        user_id=user_id,
        user_email=body.email,
        webauthn_user_id=webauthn_user_id,
    )
    return {
        "options": result["options"],
        "challenge_key": result["challenge_key"],
        "user_id": user_id,
        "webauthn_user_id": result.get("webauthn_user_id"),
    }


class PasskeyRegisterCompleteRequest(BaseModel):
    user_id: str
    credential: str  # JSON string of PublicKeyCredential
    challenge_key: str
    webauthn_user_id: str | None = None


@router.post("/api/auth/passkey/register/complete")
async def passkey_register_complete(
    body: PasskeyRegisterCompleteRequest,
    request: Request,
    response: Response,
) -> dict[str, str]:
    """Complete passkey registration and create a session."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        raise HTTPException(status_code=400, detail="Passkey auth not enabled")

    from breakthevibe.web.dependencies import passkey_service, user_repo

    if passkey_service is None or user_repo is None:
        raise HTTPException(status_code=500, detail="Passkey service not configured")

    try:
        await passkey_service.complete_registration(
            user_id=body.user_id,
            credential_json=body.credential,
            challenge_key=body.challenge_key,
            webauthn_user_id_hex=body.webauthn_user_id,
        )
    except Exception as exc:
        logger.warning("passkey_registration_failed", error=str(exc))
        raise HTTPException(status_code=400, detail="Registration failed") from exc

    # Create session
    user = await user_repo.get_by_id(body.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    org_role = await user_repo.get_user_org_role(body.user_id)
    org_id = org_role[0] if org_role else SENTINEL_ORG_ID
    role = org_role[1] if org_role else "admin"

    auth = get_session_auth()
    token = auth.create_session(
        user.email,
        user_id=user.id,
        org_id=org_id,
        role=role,
        email=user.email,
    )
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=86400,
    )
    await audit(
        org_id=org_id,
        user_id=user.id,
        action="auth.register",
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("passkey_registered_and_logged_in", user_id=user.id, email=user.email)
    return {"status": "ok", "email": user.email}


@router.post("/api/auth/passkey/authenticate/begin")
async def passkey_authenticate_begin(request: Request) -> dict[str, Any]:
    """Begin passkey authentication ceremony."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        raise HTTPException(status_code=400, detail="Passkey auth not enabled")

    from breakthevibe.web.dependencies import passkey_service

    if passkey_service is None:
        raise HTTPException(status_code=500, detail="Passkey service not configured")

    # Optionally accept email to scope credentials
    body: dict[str, Any] = {}
    if request.headers.get("content-type") == "application/json":
        body = await request.json()
    email: str | None = body.get("email") if isinstance(body, dict) else None

    result = await passkey_service.begin_authentication(email=email)
    return {
        "options": result["options"],
        "challenge_key": result["challenge_key"],
    }


class PasskeyAuthCompleteRequest(BaseModel):
    credential: str  # JSON string of PublicKeyCredential
    challenge_key: str


@router.post("/api/auth/passkey/authenticate/complete")
async def passkey_authenticate_complete(
    body: PasskeyAuthCompleteRequest,
    request: Request,
    response: Response,
) -> dict[str, str]:
    """Complete passkey authentication and create a session."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        raise HTTPException(status_code=400, detail="Passkey auth not enabled")

    from breakthevibe.web.dependencies import passkey_service, user_repo

    if passkey_service is None or user_repo is None:
        raise HTTPException(status_code=500, detail="Passkey service not configured")

    try:
        user_id = await passkey_service.complete_authentication(
            credential_json=body.credential,
            challenge_key=body.challenge_key,
        )
    except Exception as exc:
        logger.warning("passkey_auth_failed", error=str(exc))
        raise HTTPException(status_code=400, detail="Authentication failed") from exc

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    org_role = await user_repo.get_user_org_role(user_id)
    org_id = org_role[0] if org_role else SENTINEL_ORG_ID
    role = org_role[1] if org_role else "admin"

    auth = get_session_auth()
    token = auth.create_session(
        user.email,
        user_id=user.id,
        org_id=org_id,
        role=role,
        email=user.email,
    )
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=86400,
    )
    await audit(
        org_id=org_id,
        user_id=user.id,
        action="auth.login",
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("user_logged_in_passkey", user_id=user.id, email=user.email)
    return {"status": "ok", "email": user.email}


# ---------------------------------------------------------------------------
# Bootstrap check
# ---------------------------------------------------------------------------


@router.get("/api/auth/bootstrap-status")
async def bootstrap_status() -> dict[str, bool]:
    """Check if the system needs initial setup (no users with passkeys)."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        return {"needs_setup": False, "passkey_mode": False}

    from breakthevibe.web.dependencies import passkey_service

    if passkey_service is None:
        return {"needs_setup": False, "passkey_mode": True}

    has_credentials = await passkey_service.has_any_credentials()
    return {"needs_setup": not has_credentials, "passkey_mode": True}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Destroy the current session."""
    auth = get_session_auth()
    token = request.cookies.get("session")
    if token:
        auth.destroy_session(token)
    response.delete_cookie("session")
    await audit(
        org_id=SENTINEL_ORG_ID,
        user_id="",
        action="auth.logout",
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    return {"status": "logged_out"}
