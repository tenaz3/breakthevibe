"""Clerk webhook receiver for user/org/membership sync."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import get_settings
from breakthevibe.models.database import Organization, OrganizationMembership, User
from breakthevibe.storage.database import get_engine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Svix signature tolerance in seconds (5 minutes)
_SVIX_TOLERANCE = 300


def _verify_svix_signature(payload: bytes, headers: dict[str, str], secret: str) -> bool:
    """Verify Clerk/Svix webhook signature.

    Clerk uses Svix for webhook delivery. The signature format is:
    svix-id, svix-timestamp, svix-signature headers.
    """
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")

    if not msg_id or not timestamp or not signatures:
        return False

    # Check timestamp tolerance
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > _SVIX_TOLERANCE:
        logger.warning("webhook_timestamp_expired", delta=abs(time.time() - ts))
        return False

    # Svix secret starts with "whsec_" — strip prefix and decode base64
    import base64

    if secret.startswith("whsec_"):
        secret = secret[6:]
    secret_bytes = base64.b64decode(secret)

    # Compute expected signature
    to_sign = f"{msg_id}.{timestamp}.".encode() + payload
    expected = hmac.new(secret_bytes, to_sign, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()

    # Check against all provided signatures (comma-separated, prefixed with v1,)
    for sig in signatures.split(" "):
        parts = sig.split(",", 1)
        if len(parts) == 2 and parts[0] == "v1" and hmac.compare_digest(parts[1], expected_b64):
            return True
    return False


@router.post("/clerk")
async def clerk_webhook(request: Request) -> dict[str, str]:
    """Handle Clerk webhook events for user/org/membership sync."""
    settings = get_settings()
    webhook_secret = settings.clerk_webhook_secret

    # H-7: Validate webhook secret is configured
    if not webhook_secret or len(webhook_secret.strip()) < 10:
        logger.error("webhook_secret_missing_or_short")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    if not _verify_svix_signature(payload, headers, webhook_secret.strip()):
        logger.warning("webhook_signature_invalid")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = json.loads(payload)
    event_type = event.get("type", "")
    data = event.get("data", {})

    logger.info("webhook_received", event_type=event_type)

    handler = _HANDLERS.get(event_type)
    if handler:
        await handler(data)
    else:
        logger.debug("webhook_unhandled_event", event_type=event_type)

    return {"status": "ok"}


# --- Event handlers ---


async def _handle_user_created(data: dict[str, Any]) -> None:
    """Create or update a User record from Clerk user.created event."""
    clerk_user_id = data.get("id", "")
    email = _extract_primary_email(data)
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()

    async with AsyncSession(get_engine()) as session:
        stmt = select(User).where(col(User.clerk_user_id) == clerk_user_id)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            existing.email = email
            existing.name = name
            session.add(existing)
        else:
            session.add(User(clerk_user_id=clerk_user_id, email=email, name=name))
        await session.commit()
    logger.info("user_synced", clerk_user_id=clerk_user_id)


async def _handle_user_updated(data: dict[str, Any]) -> None:
    """Update User record from Clerk user.updated event."""
    await _handle_user_created(data)  # Same upsert logic


async def _handle_user_deleted(data: dict[str, Any]) -> None:
    """Deactivate user from Clerk user.deleted event."""
    clerk_user_id = data.get("id", "")
    async with AsyncSession(get_engine()) as session:
        stmt = select(User).where(col(User.clerk_user_id) == clerk_user_id)
        result = await session.execute(stmt)
        user = result.scalars().first()
        if user:
            user.is_active = False
            session.add(user)
            await session.commit()
    logger.info("user_deactivated", clerk_user_id=clerk_user_id)


async def _handle_org_created(data: dict[str, Any]) -> None:
    """Create or update Organization from Clerk organization.created event."""
    clerk_org_id = data.get("id", "")
    name = data.get("name", "")

    async with AsyncSession(get_engine()) as session:
        # C-4: Idempotent upsert
        stmt = select(Organization).where(col(Organization.clerk_org_id) == clerk_org_id)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            existing.name = name
            session.add(existing)
        else:
            session.add(Organization(clerk_org_id=clerk_org_id, name=name))
        await session.commit()
    logger.info("org_synced", clerk_org_id=clerk_org_id)


async def _handle_org_updated(data: dict[str, Any]) -> None:
    """Update Organization from Clerk organization.updated event."""
    await _handle_org_created(data)


async def _handle_org_deleted(data: dict[str, Any]) -> None:
    """Handle organization deletion (soft-delete by removing memberships)."""
    clerk_org_id = data.get("id", "")
    async with AsyncSession(get_engine()) as session:
        stmt = select(Organization).where(col(Organization.clerk_org_id) == clerk_org_id)
        result = await session.execute(stmt)
        org = result.scalars().first()
        if org:
            # Remove all memberships for this org
            mem_stmt = select(OrganizationMembership).where(
                col(OrganizationMembership.org_id) == org.id
            )
            mem_result = await session.execute(mem_stmt)
            for mem in mem_result.scalars().all():
                await session.delete(mem)
            await session.commit()
    logger.info("org_deleted", clerk_org_id=clerk_org_id)


async def _handle_membership_created(data: dict[str, Any]) -> None:
    """Create membership from Clerk organizationMembership.created event."""
    clerk_org_id = data.get("organization", {}).get("id", "")
    clerk_user_id = data.get("public_user_data", {}).get("user_id", "")
    role = data.get("role", "member")

    # Map Clerk roles to our roles
    role_map = {"org:admin": "admin", "org:member": "member", "org:viewer": "viewer"}
    mapped_role = role_map.get(role, "member")

    async with AsyncSession(get_engine()) as session:
        # Look up org and user
        org_stmt = select(Organization).where(col(Organization.clerk_org_id) == clerk_org_id)
        org_result = await session.execute(org_stmt)
        org = org_result.scalars().first()

        user_stmt = select(User).where(col(User.clerk_user_id) == clerk_user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalars().first()

        if not org or not user:
            logger.warning(
                "membership_sync_missing_entity",
                clerk_org_id=clerk_org_id,
                clerk_user_id=clerk_user_id,
                org_found=bool(org),
                user_found=bool(user),
            )
            return

        # C-4: Idempotent upsert — check existing membership
        mem_stmt = select(OrganizationMembership).where(
            col(OrganizationMembership.org_id) == org.id,
            col(OrganizationMembership.user_id) == user.id,
        )
        mem_result = await session.execute(mem_stmt)
        existing = mem_result.scalars().first()
        if existing:
            existing.role = mapped_role
            session.add(existing)
        else:
            session.add(OrganizationMembership(org_id=org.id, user_id=user.id, role=mapped_role))
        await session.commit()
    logger.info("membership_synced", clerk_org_id=clerk_org_id, clerk_user_id=clerk_user_id)


async def _handle_membership_updated(data: dict[str, Any]) -> None:
    """Update membership role from Clerk organizationMembership.updated event."""
    await _handle_membership_created(data)


async def _handle_membership_deleted(data: dict[str, Any]) -> None:
    """Remove membership from Clerk organizationMembership.deleted event."""
    clerk_org_id = data.get("organization", {}).get("id", "")
    clerk_user_id = data.get("public_user_data", {}).get("user_id", "")

    async with AsyncSession(get_engine()) as session:
        org_stmt = select(Organization).where(col(Organization.clerk_org_id) == clerk_org_id)
        org_result = await session.execute(org_stmt)
        org = org_result.scalars().first()

        user_stmt = select(User).where(col(User.clerk_user_id) == clerk_user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalars().first()

        if org and user:
            mem_stmt = select(OrganizationMembership).where(
                col(OrganizationMembership.org_id) == org.id,
                col(OrganizationMembership.user_id) == user.id,
            )
            mem_result = await session.execute(mem_stmt)
            membership = mem_result.scalars().first()
            if membership:
                await session.delete(membership)
                await session.commit()
    logger.info("membership_removed", clerk_org_id=clerk_org_id, clerk_user_id=clerk_user_id)


def _extract_primary_email(data: dict[str, Any]) -> str:
    """Extract primary email from Clerk user data."""
    email_addresses = data.get("email_addresses", [])
    primary_id = data.get("primary_email_address_id", "")
    for addr in email_addresses:
        if addr.get("id") == primary_id:
            return str(addr.get("email_address", ""))
    if email_addresses:
        return str(email_addresses[0].get("email_address", ""))
    return ""


# Handler dispatch map
_HANDLERS: dict[str, Any] = {
    "user.created": _handle_user_created,
    "user.updated": _handle_user_updated,
    "user.deleted": _handle_user_deleted,
    "organization.created": _handle_org_created,
    "organization.updated": _handle_org_updated,
    "organization.deleted": _handle_org_deleted,
    "organizationMembership.created": _handle_membership_created,
    "organizationMembership.updated": _handle_membership_updated,
    "organizationMembership.deleted": _handle_membership_deleted,
}
