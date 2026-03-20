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

# Incremented on every audit write failure — queryable without external metrics
_audit_failures: int = 0


def _sanitize_details(details: dict[str, Any]) -> str:
    """Strip sensitive fields and enforce size limit (M-3).

    Truncation is done by progressively dropping values that exceed the budget
    rather than slicing the JSON string, which would produce invalid JSON.
    """
    sanitized = {k: v for k, v in details.items() if k.lower() not in _SENSITIVE_FIELDS}
    encoded = json.dumps(sanitized, default=str)
    if len(encoded) <= _MAX_DETAILS_BYTES:
        return encoded
    # Truncate by replacing oversized string values, then fall back to
    # dropping keys until the serialised form fits within the budget.
    truncated: dict[str, Any] = {}
    for k, v in sanitized.items():
        candidate = json.dumps({**truncated, k: v}, default=str)
        if len(candidate) <= _MAX_DETAILS_BYTES:
            truncated[k] = v
        else:
            # Try storing a string representation trimmed to a safe length
            short_v = str(v)[
                : max(0, _MAX_DETAILS_BYTES - len(json.dumps(truncated, default=str)) - len(k) - 10)
            ]
            truncated[k] = short_v + "...[truncated]"
            break
    return json.dumps(truncated, default=str)


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
            global _audit_failures
            _audit_failures += 1
            logger.exception(
                "audit_log_failed",
                action=action,
                org_id=org_id,
                total_failures=_audit_failures,
            )


_audit_logger: AuditLogger | None = None


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
    """Convenience wrapper — logs audit entry to the database."""
    global _audit_logger
    if _audit_logger is None:
        from breakthevibe.storage.database import get_engine

        _audit_logger = AuditLogger(get_engine())
    await _audit_logger.log(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        request_id=request_id,
    )
