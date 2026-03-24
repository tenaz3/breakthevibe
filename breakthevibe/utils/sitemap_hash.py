"""Stable hashing for SiteMap cache keying."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from breakthevibe.models.domain import SiteMap


def compute_sitemap_hash(sitemap: SiteMap) -> str:
    """Compute a stable SHA-256 hex digest of a SiteMap.

    Uses sorted keys and stringified values to ensure determinism
    across runs regardless of field ordering or float precision.
    """
    payload = json.dumps(sitemap.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
