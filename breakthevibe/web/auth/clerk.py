"""Clerk JWT validation and JWKS key management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import structlog

from breakthevibe.config.settings import get_settings

logger = structlog.get_logger(__name__)

# JWKS cache TTL in seconds (1 hour)
_JWKS_CACHE_TTL = 3600


@dataclass
class _JWKSCache:
    """In-memory cache for Clerk JWKS keys."""

    keys: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        return time.monotonic() - self.fetched_at > _JWKS_CACHE_TTL


_cache = _JWKSCache()


async def _fetch_jwks(jwks_url: str) -> list[dict[str, Any]]:
    """Fetch JWKS from Clerk and update cache."""
    global _cache  # noqa: PLW0603
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            keys: list[dict[str, Any]] = resp.json().get("keys", [])
            _cache = _JWKSCache(keys=keys, fetched_at=time.monotonic())
            logger.debug("jwks_fetched", key_count=len(keys))
            return keys
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("jwks_fetch_failed", error=str(exc))
        # Return stale cache if available (C-3)
        if _cache.keys:
            logger.info("jwks_using_stale_cache")
            return _cache.keys
        raise


async def _get_signing_keys() -> list[dict[str, Any]]:
    """Get JWKS keys, using cache when fresh."""
    settings = get_settings()
    jwks_url = settings.clerk_jwks_url
    if not jwks_url:
        msg = "CLERK_JWKS_URL is not configured"
        raise ValueError(msg)

    if not _cache.is_stale and _cache.keys:
        return _cache.keys

    return await _fetch_jwks(jwks_url)


@dataclass(frozen=True, slots=True)
class ClerkClaims:
    """Parsed and validated claims from a Clerk JWT."""

    sub: str  # Clerk user ID
    org_id: str | None  # Clerk org ID (if in org context)
    org_role: str | None  # Clerk org role
    email: str
    name: str


async def verify_clerk_token(token: str) -> ClerkClaims:
    """Verify a Clerk JWT and return parsed claims.

    Raises jwt.PyJWTError on invalid/expired tokens.
    """
    settings = get_settings()
    keys = await _get_signing_keys()

    # Build the JWKS client for PyJWT
    jwk_set = {"keys": keys}
    signing_key = jwt.PyJWKSet.from_dict(jwk_set)

    # Decode options
    decode_options: dict[str, Any] = {
        "algorithms": ["RS256"],
        "options": {"verify_aud": False},
    }
    if settings.clerk_issuer:
        decode_options["issuer"] = settings.clerk_issuer

    # Try each key until one works
    last_error: Exception | None = None
    for jwk in signing_key.keys:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                jwk.key,
                **decode_options,
            )
            return ClerkClaims(
                sub=payload["sub"],
                org_id=payload.get("org_id"),
                org_role=payload.get("org_role"),
                email=payload.get("email", ""),
                name=payload.get("name", ""),
            )
        except jwt.PyJWTError as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    msg = "No valid signing key found"
    raise jwt.InvalidTokenError(msg)
