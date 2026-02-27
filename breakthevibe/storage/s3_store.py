"""S3/R2-compatible object store implementation via aiobotocore."""

from __future__ import annotations

from typing import Any

import structlog
from aiobotocore.session import get_session

from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


class S3ObjectStore(ObjectStore):
    """Object store backed by S3-compatible storage (AWS S3, Cloudflare R2, MinIO)."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str = "auto",
    ) -> None:
        self._bucket = bucket
        self._session = get_session()
        self._config: dict[str, Any] = {
            "region_name": region,
        }
        if endpoint_url:
            self._config["endpoint_url"] = endpoint_url
        if access_key_id:
            self._config["aws_access_key_id"] = access_key_id
        if secret_access_key:
            self._config["aws_secret_access_key"] = secret_access_key

    async def put(self, key: str, data: bytes) -> None:
        """Upload data to S3."""
        async with self._session.create_client("s3", **self._config) as client:
            await client.put_object(Bucket=self._bucket, Key=key, Body=data)
        logger.debug("s3_put", key=key, size=len(data), bucket=self._bucket)

    async def get(self, key: str) -> bytes | None:
        """Download data from S3. Returns None if not found."""
        async with self._session.create_client("s3", **self._config) as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                async with resp["Body"] as stream:
                    data: bytes = await stream.read()
                return data
            except client.exceptions.NoSuchKey:
                return None

    async def delete(self, key: str) -> None:
        """Delete an object from S3."""
        async with self._session.create_client("s3", **self._config) as client:
            # If key looks like a prefix, delete all objects under it
            if key.endswith("/"):
                await self._delete_prefix(client, key)
            else:
                await client.delete_object(Bucket=self._bucket, Key=key)

    async def _delete_prefix(self, client: Any, prefix: str) -> None:
        """Delete all objects under a prefix."""
        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                delete_req = {"Objects": [{"Key": obj["Key"]} for obj in objects]}
                await client.delete_objects(Bucket=self._bucket, Delete=delete_req)

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys under a prefix."""
        keys: list[str] = []
        async with self._session.create_client("s3", **self._config) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        return sorted(keys)

    async def get_usage_bytes(self, prefix: str = "") -> int:
        """Get total storage usage in bytes for keys under prefix."""
        total = 0
        async with self._session.create_client("s3", **self._config) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    total += obj.get("Size", 0)
        return total
