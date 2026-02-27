"""Abstract object store interface for binary artifact storage."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStore(ABC):
    """Abstract base class for object/blob storage."""

    @abstractmethod
    async def put(self, key: str, data: bytes) -> None:
        """Store binary data at the given key."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Retrieve binary data by key. Returns None if not found."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the object at the given key."""

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys matching the given prefix."""

    @abstractmethod
    async def get_usage_bytes(self, prefix: str = "") -> int:
        """Get total storage usage in bytes for keys matching prefix."""


def create_object_store() -> ObjectStore:
    """Factory: create the appropriate ObjectStore based on settings."""
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if settings.use_s3:
        from breakthevibe.storage.s3_store import S3ObjectStore

        return S3ObjectStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )

    from pathlib import Path

    from breakthevibe.storage.local_store import LocalObjectStore

    return LocalObjectStore(base_dir=Path(settings.artifacts_dir).expanduser())
