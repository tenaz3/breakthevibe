"""Cookie-based session authentication backed by the database."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import Session as DbSession

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_AGE_HOURS = 24


class SessionAuth:
    """Database-backed cookie session management.

    The cookie value is token.hmac_signature so the server can verify it
    has not been tampered with before hitting the database.
    """

    def __init__(self, secret_key: str, max_age_hours: int = _DEFAULT_MAX_AGE_HOURS) -> None:
        self._secret = secret_key.encode()
        self._max_age_hours = max_age_hours

    async def create_session(self, username: str, **extra: Any) -> str:
        """Insert a new session row and return the signed cookie value.

        Args:
            username: Human-readable identifier stored in session data.
            **extra: Additional fields (user_id, org_id, role, email) stored
                     in the session data_json blob.

        Returns:
            Signed cookie value token.signature.
        """
        from breakthevibe.storage.database import get_engine

        raw_token = secrets.token_urlsafe(32)
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=self._max_age_hours)

        data: dict[str, Any] = {"username": username, **extra}
        org_id: str = str(extra.get("org_id", SENTINEL_ORG_ID))
        user_id: str = str(extra.get("user_id", username))

        db_session = DbSession(
            id=raw_token,
            user_id=user_id,
            org_id=org_id,
            data_json=json.dumps(data),
            expires_at=expires,
        )

        engine = get_engine()
        async with AsyncSession(engine) as db, db.begin():
            db.add(db_session)

        logger.info("session_created", username=username, user_id=user_id)
        return self._sign_token(raw_token)

    async def validate_session(self, token: str) -> dict[str, Any] | None:
        """Validate a signed cookie value and return session data.

        Args:
            token: The signed cookie value token.signature.

        Returns:
            Session data dict, or None if invalid or expired.
        """
        raw_token = self._verify_signature(token)
        if raw_token is None:
            return None

        from breakthevibe.storage.database import get_engine

        now = datetime.now(UTC).replace(tzinfo=None)
        engine = get_engine()
        async with AsyncSession(engine) as db:
            result = await db.execute(
                select(DbSession).where(
                    col(DbSession.id) == raw_token,
                    col(DbSession.expires_at) > now,
                )
            )
            row = result.scalars().first()

        if row is None:
            return None

        try:
            return json.loads(row.data_json)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, AttributeError):
            logger.warning("session_data_corrupt", raw_token=raw_token)
            return None

    async def destroy_session(self, token: str) -> None:
        """Delete a session row from the database.

        Args:
            token: The signed cookie value token.signature.
        """
        raw_token = self._verify_signature(token)
        if raw_token is None:
            return

        from breakthevibe.storage.database import get_engine

        engine = get_engine()
        async with AsyncSession(engine) as db, db.begin():
            await db.execute(delete(DbSession).where(col(DbSession.id) == raw_token))

        logger.info("session_destroyed")

    @staticmethod
    async def cleanup_expired() -> int:
        """Delete all expired sessions from the database.

        Returns:
            Number of rows deleted.
        """
        from breakthevibe.storage.database import get_engine

        now = datetime.now(UTC).replace(tzinfo=None)
        engine = get_engine()
        async with AsyncSession(engine) as db, db.begin():
            result = await db.execute(delete(DbSession).where(col(DbSession.expires_at) <= now))
        deleted: int = result.rowcount  # type: ignore[attr-defined]
        logger.info("expired_sessions_cleaned", count=deleted)
        return deleted

    def _sign_token(self, raw_token: str) -> str:
        """Return token.signature."""
        return f"{raw_token}.{self._sign(raw_token)}"

    def _verify_signature(self, token: str) -> str | None:
        """Verify HMAC signature and return the raw token, or None."""
        if not token or "." not in token:
            return None
        raw_token, signature = token.rsplit(".", 1)
        expected = self._sign(raw_token)
        if not hmac.compare_digest(signature, expected):
            return None
        return raw_token

    def _sign(self, data: str) -> str:
        """Create a short HMAC-SHA256 signature."""
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()[:32]


_auth_instance: SessionAuth | None = None


def get_session_auth() -> SessionAuth:
    """Return (or lazily create) the process-wide SessionAuth singleton."""
    global _auth_instance  # noqa: PLW0603
    if _auth_instance is None:
        from breakthevibe.config.settings import get_settings

        settings = get_settings()
        _auth_instance = SessionAuth(secret_key=settings.secret_key)
    return _auth_instance


async def require_auth(request: Request) -> dict[str, Any]:
    """FastAPI dependency that enforces session authentication.

    Checks the session cookie for a valid signed token.
    Raises 401 if unauthenticated.
    """
    auth = get_session_auth()
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await auth.validate_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


async def require_auth_page(request: Request) -> dict[str, Any]:
    """Like require_auth but redirects to /login for browser page requests."""
    from urllib.parse import quote

    auth = get_session_auth()
    token = request.cookies.get("session")
    user = await auth.validate_session(token) if token else None
    if not user:
        next_url = quote(str(request.url.path), safe="/")
        raise HTTPException(
            status_code=307,
            headers={"Location": f"/login?next={next_url}"},
        )
    return user
