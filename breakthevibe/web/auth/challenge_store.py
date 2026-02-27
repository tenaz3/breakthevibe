"""Short-lived challenge storage for WebAuthn ceremonies."""

from __future__ import annotations

import time


class InMemoryChallengeStore:
    """Stores WebAuthn challenges with TTL expiry.

    Challenges are one-time-use: ``pop`` retrieves and deletes.
    Expired entries are lazily cleaned on ``set`` and ``pop``.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, float]] = {}  # key -> (challenge, expires_at)

    def set(self, key: str, challenge: bytes, ttl_seconds: int = 90) -> None:
        """Store a challenge with a TTL."""
        self._cleanup()
        self._store[key] = (challenge, time.time() + ttl_seconds)

    def pop(self, key: str) -> bytes | None:
        """Retrieve and delete a challenge. Returns None if missing or expired."""
        self._cleanup()
        entry = self._store.pop(key, None)
        if entry is None:
            return None
        challenge, expires_at = entry
        if time.time() > expires_at:
            return None
        return challenge

    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
