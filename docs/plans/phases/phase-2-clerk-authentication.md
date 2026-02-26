# Phase 2: Clerk Authentication Integration

> **Status**: Not started
> **Depends on**: Phase 1 (Multi-Tenancy Foundation)
> **Estimated scope**: ~5 files created, ~3 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Replace the single-admin HMAC cookie auth with Clerk JWT validation for multi-tenant mode. Implement a webhook handler to sync users, organizations, and memberships from Clerk to our database. Maintain backward compatibility via `AUTH_MODE=single`.

---

## 2. Prerequisites

- Phase 1 complete (Organization, User, OrganizationMembership tables exist)
- Clerk account created with:
  - An application configured
  - Organizations feature enabled
  - Webhook endpoint registered (use ngrok for dev)
- Environment variables ready: `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `CLERK_ISSUER`, `CLERK_JWKS_URL`

---

## 3. New Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "PyJWT>=2.8.0",
    "cryptography>=43.0.0",
]
```

`httpx` is already a dependency (used for JWKS fetching).

---

## 4. Detailed Implementation

### 4.1 Clerk JWT Validation

**Create: `breakthevibe/web/auth/clerk.py`**

```python
"""Clerk JWT validation and tenant resolution."""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import structlog
from fastapi import HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.models.database import Organization, OrganizationMembership, User
from breakthevibe.storage.database import get_engine
from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

# JWKS cache
_JWKS_CACHE: dict[str, Any] = {}
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL: float = 3600.0  # 1 hour


async def _fetch_jwks(clerk_jwks_url: str, force: bool = False) -> dict[str, Any]:
    """Fetch Clerk JWKS, cached for 1 hour."""
    global _JWKS_CACHE, _JWKS_FETCHED_AT  # noqa: PLW0603
    now = time.monotonic()
    if not force and _JWKS_CACHE and (now - _JWKS_FETCHED_AT) < _JWKS_TTL:
        return _JWKS_CACHE
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(clerk_jwks_url)
        resp.raise_for_status()
    _JWKS_CACHE = resp.json()
    _JWKS_FETCHED_AT = now
    logger.info("clerk_jwks_refreshed")
    return _JWKS_CACHE


def _decode_clerk_jwt(
    token: str, jwks: dict[str, Any], audience: str | None, issuer: str
) -> dict[str, Any]:
    """Decode and verify a Clerk RS256 JWT."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = None
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
            break
    if key is None:
        raise jwt.InvalidTokenError("No matching JWK found for kid")

    decode_opts: dict[str, Any] = {
        "algorithms": ["RS256"],
        "issuer": issuer,
        "options": {"require": ["exp", "iat", "sub"]},
    }
    if audience:
        decode_opts["audience"] = audience
    return jwt.decode(token, key=key, **decode_opts)


async def _resolve_tenant(claims: dict[str, Any]) -> TenantContext:
    """Look up internal User/Org/Membership from Clerk JWT claims."""
    clerk_user_id: str = claims["sub"]
    clerk_org_id: str | None = claims.get("org_id")
    clerk_role_raw: str = claims.get("org_role", "org:viewer")
    role = clerk_role_raw.split(":")[-1] if ":" in clerk_role_raw else clerk_role_raw

    engine = get_engine()
    async with AsyncSession(engine) as session:
        # Resolve User
        stmt = select(User).where(
            User.clerk_user_id == clerk_user_id,
            User.deleted_at.is_(None),
        )
        user = (await session.execute(stmt)).scalars().first()
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not provisioned. Try signing out and back in.",
            )

        if not clerk_org_id:
            raise HTTPException(
                status_code=403,
                detail="No active organization. Select an organization in Clerk.",
            )

        # Resolve Organization
        stmt = select(Organization).where(
            Organization.clerk_org_id == clerk_org_id,
            Organization.is_active.is_(True),
            Organization.deleted_at.is_(None),
        )
        org = (await session.execute(stmt)).scalars().first()
        if not org:
            raise HTTPException(
                status_code=403, detail="Organization not found or inactive."
            )

        # Resolve Membership
        stmt = select(OrganizationMembership).where(
            OrganizationMembership.org_id == org.id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
        )
        membership = (await session.execute(stmt)).scalars().first()
        if not membership:
            raise HTTPException(
                status_code=403, detail="Not a member of this organization."
            )

    return TenantContext(
        org_id=org.id,
        clerk_org_id=clerk_org_id,
        user_id=user.id,
        clerk_user_id=clerk_user_id,
        role=role,
        email=claims.get("email", user.email),
    )


async def require_clerk_auth(request: Request) -> TenantContext:
    """FastAPI dependency for Clerk-authenticated routes.

    Reads Bearer token from Authorization header or __session cookie.
    """
    from breakthevibe.config.settings import get_settings

    settings = get_settings()

    # Extract token
    token: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("__session")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Decode JWT (with one retry on JWKS cache miss)
    jwks = await _fetch_jwks(settings.clerk_jwks_url or "")
    try:
        claims = _decode_clerk_jwt(
            token, jwks,
            audience=settings.clerk_audience,
            issuer=settings.clerk_issuer or "",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        # Retry with fresh JWKS (key rotation)
        jwks = await _fetch_jwks(settings.clerk_jwks_url or "", force=True)
        try:
            claims = _decode_clerk_jwt(
                token, jwks,
                audience=settings.clerk_audience,
                issuer=settings.clerk_issuer or "",
            )
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    return await _resolve_tenant(claims)
```

### 4.2 Clerk Webhook Handler

**Create: `breakthevibe/web/auth/webhook.py`**

```python
"""Clerk webhook receiver — syncs users and org memberships to our DB.

Events handled:
  - user.created / user.updated / user.deleted
  - organization.created / organization.updated / organization.deleted
  - organizationMembership.created / updated / deleted
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.models.database import Organization, OrganizationMembership, User
from breakthevibe.storage.database import get_engine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/webhooks/clerk", tags=["webhooks"])


def _verify_svix_signature(
    payload: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
    webhook_secret: str,
) -> bool:
    """Verify Svix webhook signature (used by Clerk)."""
    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + payload
    secret_bytes = base64.b64decode(
        webhook_secret.removeprefix("whsec_") + "=="
    )
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode()
    for sig_entry in svix_signature.split(" "):
        if sig_entry.startswith("v1,"):
            if hmac.compare_digest(sig_entry[3:], expected):
                return True
    return False


@router.post("/")
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(alias="svix-id"),
    svix_timestamp: str = Header(alias="svix-timestamp"),
    svix_signature: str = Header(alias="svix-signature"),
) -> dict[str, str]:
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    payload = await request.body()

    # Verify signature
    if not _verify_svix_signature(
        payload, svix_id, svix_timestamp, svix_signature,
        settings.clerk_webhook_secret or "",
    ):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Reject replays older than 5 minutes
    try:
        ts = int(svix_timestamp)
        if abs(time.time() - ts) > 300:
            raise HTTPException(status_code=400, detail="Webhook timestamp too old")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    event = json.loads(payload)
    event_type: str = event.get("type", "")
    data: dict[str, Any] = event.get("data", {})

    logger.info("clerk_webhook_received", event_type=event_type)

    engine = get_engine()
    async with AsyncSession(engine) as session:
        handler = _HANDLERS.get(event_type)
        if handler:
            await handler(session, data)
            await session.commit()
        else:
            logger.debug("clerk_webhook_unhandled", event_type=event_type)

    return {"status": "ok"}


# --- Event Handlers ---


async def _upsert_user(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_user_id = data["id"]
    email = ""
    for em in data.get("email_addresses", []):
        if em.get("id") == data.get("primary_email_address_id"):
            email = em.get("email_address", "")
            break

    display_name = (
        f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or None
    )

    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        existing.email = email
        existing.display_name = display_name
        existing.avatar_url = data.get("image_url")
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        session.add(
            User(
                clerk_user_id=clerk_user_id,
                email=email,
                display_name=display_name,
                avatar_url=data.get("image_url"),
            )
        )
    logger.info("user_upserted", clerk_user_id=clerk_user_id, email=email)


async def _soft_delete_user(session: AsyncSession, data: dict[str, Any]) -> None:
    """GDPR: anonymize PII, keep row for FK integrity."""
    clerk_user_id = data["id"]
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    user = (await session.execute(stmt)).scalars().first()
    if user:
        user.email = f"deleted_{user.id}@erased.invalid"
        user.display_name = None
        user.avatar_url = None
        user.deleted_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        session.add(user)
    logger.info("user_soft_deleted", clerk_user_id=clerk_user_id)


async def _upsert_org(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_org_id = data["id"]
    stmt = select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        existing.name = data.get("name", existing.name)
        existing.slug = data.get("slug", existing.slug)
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        session.add(
            Organization(
                clerk_org_id=clerk_org_id,
                name=data.get("name", ""),
                slug=data.get("slug", clerk_org_id),
            )
        )
    logger.info("org_upserted", clerk_org_id=clerk_org_id)


async def _soft_delete_org(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_org_id = data["id"]
    stmt = select(Organization).where(Organization.clerk_org_id == clerk_org_id)
    org = (await session.execute(stmt)).scalars().first()
    if org:
        org.is_active = False
        org.deleted_at = datetime.now(UTC)
        org.updated_at = datetime.now(UTC)
        session.add(org)
    logger.info("org_soft_deleted", clerk_org_id=clerk_org_id)


async def _upsert_membership(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_membership_id = data["id"]
    clerk_user_id = data["public_user_data"]["user_id"]
    clerk_org_id = data["organization"]["id"]
    role_raw: str = data.get("role", "org:member")
    role = role_raw.split(":")[-1] if ":" in role_raw else role_raw

    # Resolve local IDs
    user = (
        (await session.execute(select(User).where(User.clerk_user_id == clerk_user_id)))
        .scalars()
        .first()
    )
    org = (
        (
            await session.execute(
                select(Organization).where(Organization.clerk_org_id == clerk_org_id)
            )
        )
        .scalars()
        .first()
    )

    if not user or not org:
        logger.warning(
            "membership_upsert_skipped_missing_refs",
            clerk_user_id=clerk_user_id,
            clerk_org_id=clerk_org_id,
        )
        return

    stmt = select(OrganizationMembership).where(
        OrganizationMembership.clerk_membership_id == clerk_membership_id
    )
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        existing.role = role
        existing.is_active = True
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        session.add(
            OrganizationMembership(
                org_id=org.id,
                user_id=user.id,
                clerk_membership_id=clerk_membership_id,
                role=role,
            )
        )
    logger.info(
        "membership_upserted", clerk_membership_id=clerk_membership_id, role=role
    )


async def _deactivate_membership(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_membership_id = data["id"]
    stmt = select(OrganizationMembership).where(
        OrganizationMembership.clerk_membership_id == clerk_membership_id
    )
    m = (await session.execute(stmt)).scalars().first()
    if m:
        m.is_active = False
        m.updated_at = datetime.now(UTC)
        session.add(m)
    logger.info("membership_deactivated", clerk_membership_id=clerk_membership_id)


# Event type -> handler mapping
_HANDLERS: dict[str, Any] = {
    "user.created": _upsert_user,
    "user.updated": _upsert_user,
    "user.deleted": _soft_delete_user,
    "organization.created": _upsert_org,
    "organization.updated": _upsert_org,
    "organization.deleted": _soft_delete_org,
    "organizationMembership.created": _upsert_membership,
    "organizationMembership.updated": _upsert_membership,
    "organizationMembership.deleted": _deactivate_membership,
}
```

### 4.3 App Factory — Conditional Webhook Mount

**Modify: `breakthevibe/web/app.py`**

Add after auth_router inclusion:

```python
# Clerk webhook endpoint (public — signature verified inside handler)
if settings.auth_mode == "clerk":
    from breakthevibe.web.auth.webhook import router as webhook_router
    app.include_router(webhook_router)
```

---

## 5. Clerk Dashboard Configuration

### 5.1 Create Application
1. Go to clerk.com, create application
2. Enable "Organizations" in sidebar
3. Configure roles: `org:admin`, `org:member`, `org:viewer`

### 5.2 Configure Webhooks
1. Go to Webhooks in Clerk dashboard
2. Add endpoint: `https://<your-domain>/api/webhooks/clerk/`
3. Select events:
   - `user.created`, `user.updated`, `user.deleted`
   - `organization.created`, `organization.updated`, `organization.deleted`
   - `organizationMembership.created`, `organizationMembership.updated`, `organizationMembership.deleted`
4. Copy the signing secret (`whsec_...`) to `CLERK_WEBHOOK_SECRET`

### 5.3 Get API Keys
- `CLERK_SECRET_KEY`: Backend API key (`sk_live_...`)
- `CLERK_PUBLISHABLE_KEY`: Frontend key (`pk_live_...`)
- `CLERK_ISSUER`: `https://<your-instance>.clerk.accounts.dev`
- `CLERK_JWKS_URL`: `https://<your-instance>.clerk.accounts.dev/.well-known/jwks.json`

---

## 6. JWT Token Structure (Reference)

Clerk JWT claims:

```json
{
  "sub": "user_2abc123",
  "org_id": "org_xyz789",
  "org_role": "org:admin",
  "org_slug": "acme-corp",
  "email": "user@acme.com",
  "iss": "https://your-instance.clerk.accounts.dev",
  "aud": "your-audience",
  "exp": 1709000000,
  "iat": 1708996400
}
```

---

## 7. GDPR Compliance Details

### User Deletion (`user.deleted` webhook)
- Email replaced with `deleted_{user_id}@erased.invalid`
- `display_name` set to `None`
- `avatar_url` set to `None`
- `deleted_at` timestamp set
- Row preserved for FK integrity (test results reference user)

### Organization Deletion (`organization.deleted` webhook)
- `is_active` set to `False`
- `deleted_at` timestamp set
- Immediate effect: `require_clerk_auth` returns 403 for all members
- Full data purge: triggered separately via admin API (Phase 5)

---

## 8. Error Handling Matrix

| Scenario | HTTP Status | Detail |
|---|---|---|
| No token (no header, no cookie) | 401 | "Authentication required" |
| Expired JWT | 401 | "Token expired" |
| Invalid JWT signature | 401 | "Invalid token: ..." |
| JWKS fetch failure | 500 | Server error (log and retry) |
| User not in DB | 401 | "User not provisioned" |
| No org_id in JWT claims | 403 | "No active organization" |
| Org not found or inactive | 403 | "Organization not found or inactive" |
| User not member of org | 403 | "Not a member of this organization" |
| Invalid webhook signature | 400 | "Invalid webhook signature" |
| Webhook replay (>5 min old) | 400 | "Webhook timestamp too old" |

---

## 9. Dev Setup with ngrok

```bash
# Terminal 1: Start app
AUTH_MODE=clerk CLERK_SECRET_KEY=sk_test_... CLERK_WEBHOOK_SECRET=whsec_... \
  CLERK_ISSUER=https://xxx.clerk.accounts.dev \
  CLERK_JWKS_URL=https://xxx.clerk.accounts.dev/.well-known/jwks.json \
  USE_DATABASE=true \
  python -m breakthevibe.main

# Terminal 2: Start ngrok
ngrok http 8000

# Then set the ngrok URL as the webhook endpoint in Clerk dashboard:
# https://abc123.ngrok.io/api/webhooks/clerk/
```

---

## 10. Verification Checklist

- [ ] `PyJWT` and `cryptography` installed
- [ ] `AUTH_MODE=clerk` starts without errors (with all Clerk env vars)
- [ ] `AUTH_MODE=single` still works (no Clerk env vars needed)
- [ ] Valid Clerk JWT returns correct TenantContext
- [ ] Expired JWT returns 401
- [ ] JWT with no org_id returns 403
- [ ] JWKS cache works (second request doesn't fetch)
- [ ] JWKS refresh on key rotation (forced refetch)
- [ ] Webhook: `user.created` creates User row
- [ ] Webhook: `organization.created` creates Organization row
- [ ] Webhook: `organizationMembership.created` creates membership
- [ ] Webhook: `user.deleted` anonymizes PII
- [ ] Webhook: `organization.deleted` sets is_active=false
- [ ] Webhook: invalid signature returns 400
- [ ] Webhook: replay attack (old timestamp) returns 400

---

## 11. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/web/auth/clerk.py` (~130 lines) |
| CREATE | `breakthevibe/web/auth/webhook.py` (~200 lines) |
| MODIFY | `breakthevibe/web/app.py` (+5 lines, webhook router) |
| MODIFY | `pyproject.toml` (+2 dependencies) |
| MODIFY | `.env.example` (+6 Clerk variables) |
