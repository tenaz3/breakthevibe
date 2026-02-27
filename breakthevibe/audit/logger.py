"""Audit logger — immutable, insert-only audit trail.

Uses its own DB session so audit entries survive transaction rollbacks.
M-3: Details JSON is sanitized (sensitive fields stripped, 10KB max).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

# Fields to strip from details_json (M-3)
_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "api_secret",
        "access_key",
        "secret_key",
        "authorization",
        "cookie",
        "session",
        "credit_card",
        "ssn",
    }
)

_MAX_DETAILS_BYTES = 10_240  # 10KB


def _sanitize_details(details: dict[str, Any]) -> str:
    """Strip sensitive fields and enforce size limit (M-3)."""
    sanitized = {k: v for k, v in details.items() if k.lower() not in _SENSITIVE_FIELDS}
    encoded = json.dumps(sanitized, default=str)
    if len(encoded) > _MAX_DETAILS_BYTES:
        encoded = encoded[:_MAX_DETAILS_BYTES]
    return encoded


class AuditLogger:
    """Insert-only audit logger with its own DB session.

    The separate session ensures audit entries persist even if the
    calling transaction rolls back.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def log(
        self,
        *,
        org_id: str,
        user_id: str,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
        ip_address: str = "",
        request_id: str = "",
    ) -> None:
        """Write an audit log entry."""
        details_json = _sanitize_details(details or {})

        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO audit_logs "
                        "(id, org_id, user_id, action, resource_type, resource_id, "
                        "details_json, ip_address, request_id, created_at) "
                        "VALUES ("
                        "gen_random_uuid()::text, :org_id, :user_id, :action, "
                        ":resource_type, :resource_id, :details_json, "
                        ":ip_address, :request_id, NOW())"
                    ),
                    {
                        "org_id": org_id,
                        "user_id": user_id,
                        "action": action,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "details_json": details_json,
                        "ip_address": ip_address,
                        "request_id": request_id,
                    },
                )
        except Exception:
            # Audit must never break the request — log and continue
            logger.exception(
                "audit_log_failed",
                action=action,
                org_id=org_id,
            )


async def audit(
    *,
    org_id: str,
    user_id: str,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: dict[str, Any] | None = None,
    ip_address: str = "",
    request_id: str = "",
) -> None:
    """Convenience wrapper — logs audit entry if database is available.

    Silently no-ops when USE_DATABASE=false (single-tenant / dev mode).
    """
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if not settings.use_database:
        return

    from breakthevibe.storage.database import get_engine

    al = AuditLogger(get_engine())
    await al.log(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        request_id=request_id,
    )
