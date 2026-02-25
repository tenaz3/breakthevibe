"""Cookie-based session authentication."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SessionAuth:
    """Simple cookie-based session management."""

    def __init__(self, secret_key: str, max_age: int = 86400) -> None:
        self._secret = secret_key.encode()
        self._max_age = max_age
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, username: str) -> str:
        """Create a new session and return the token."""
        token = secrets.token_urlsafe(32)
        signature = self._sign(token)
        signed_token = f"{token}.{signature}"

        self._sessions[signed_token] = {
            "username": username,
            "created_at": time.time(),
        }
        logger.info("session_created", username=username)
        return signed_token

    def validate_session(self, token: str) -> dict[str, Any] | None:
        """Validate a session token and return user data."""
        if not token or "." not in token:
            return None

        raw_token, signature = token.rsplit(".", 1)
        expected_sig = self._sign(raw_token)

        if not hmac.compare_digest(signature, expected_sig):
            return None

        session = self._sessions.get(token)
        if not session:
            return None

        # Check expiry
        if time.time() - session["created_at"] > self._max_age:
            self.destroy_session(token)
            return None

        return session

    def destroy_session(self, token: str) -> None:
        """Remove a session."""
        self._sessions.pop(token, None)
        logger.info("session_destroyed")

    def _sign(self, data: str) -> str:
        """Create HMAC signature for a token."""
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()[:32]
