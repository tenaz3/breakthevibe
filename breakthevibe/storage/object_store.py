"""Abstract object store interface for binary artifact storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger(__name__)


class StorageError(Exception):
    """Raised when a storage operation fails."""


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
    """Factory: create the appropriate ObjectStore based on settings.

    Validates required S3 configuration at startup when S3 storage is enabled,
    raising StorageError immediately rather than failing on first use.
    """
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if settings.use_s3:
        missing: list[str] = []
        if not settings.s3_bucket:
            missing.append("S3_BUCKET")
        if not settings.s3_region:
            missing.append("S3_REGION")
        if missing:
            msg = f"S3 storage is enabled but required config is missing: {', '.join(missing)}"
            logger.error("s3_config_invalid", missing=missing)
            raise StorageError(msg)

        logger.info(
            "s3_store_initialised",
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint_url or "aws-default",
        )

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
