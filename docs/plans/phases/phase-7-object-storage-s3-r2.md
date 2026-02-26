# Phase 7: Object Storage (S3/R2)

> **Status**: Not started
> **Depends on**: Phase 1 (needs org_id for tenant-prefixed keys)
> **Estimated scope**: ~4 files created, ~4 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Replace local filesystem artifact storage with S3/R2-compatible object storage. Tenant-prefix all object keys for data isolation. Keep local filesystem as a zero-config fallback for development.

---

## 2. Settings Additions

**Add to: `breakthevibe/config/settings.py`**

```python
# S3/R2 Object Storage
use_s3: bool = False
s3_bucket: str | None = None
s3_endpoint_url: str | None = None      # For R2 or MinIO
s3_access_key_id: str | None = None
s3_secret_access_key: str | None = None
s3_region: str = "auto"
```

Add validation:

```python
if settings.use_s3:
    if not settings.s3_bucket:
        raise RuntimeError("USE_S3=true requires S3_BUCKET to be set.")
```

---

## 3. New Dependency

**Add to `pyproject.toml`:**

```toml
"aiobotocore>=2.13.0",
```

---

## 4. Object Store Interface

**Create: `breakthevibe/storage/object_store.py`**

```python
"""Abstract interface for binary artifact storage."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStore(ABC):
    """Backend-agnostic binary storage for screenshots, videos, diffs."""

    @abstractmethod
    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Store an object. Returns the key/URL for retrieval."""
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Retrieve an object by key. Returns None if not found."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a single object."""
        ...

    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]:
        """List all keys under a prefix."""
        ...

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under a prefix. Returns count deleted."""
        ...

    @abstractmethod
    async def get_usage_bytes(self, prefix: str) -> int:
        """Get total storage size in bytes under a prefix."""
        ...
```

---

## 5. S3/R2 Implementation

**Create: `breakthevibe/storage/s3_store.py`**

```python
"""S3/R2-compatible object storage using aiobotocore."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from aiobotocore.session import get_session

from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


class S3ObjectStore(ObjectStore):
    """S3/R2-compatible object storage."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "auto",
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region
        self._session = get_session()

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[Any, None]:
        async with self._session.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name=self._region,
        ) as client:
            yield client

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        logger.debug("s3_put", key=key, size=len(data))
        return key

    async def get(self, key: str) -> bytes | None:
        async with self._client() as client:
            try:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                async with resp["Body"] as stream:
                    return await stream.read()
            except client.exceptions.NoSuchKey:
                return None

    async def delete(self, key: str) -> None:
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)
        logger.debug("s3_deleted", key=key)

    async def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        async with self._client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._bucket, Prefix=prefix
            ):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        return keys

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list_keys(prefix)
        if not keys:
            return 0
        async with self._client() as client:
            # S3 delete_objects accepts up to 1000 keys per call
            for i in range(0, len(keys), 1000):
                batch = keys[i : i + 1000]
                await client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": k} for k in batch]},
                )
        logger.info("s3_prefix_deleted", prefix=prefix, count=len(keys))
        return len(keys)

    async def get_usage_bytes(self, prefix: str) -> int:
        total = 0
        async with self._client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._bucket, Prefix=prefix
            ):
                for obj in page.get("Contents", []):
                    total += obj.get("Size", 0)
        return total
```

---

## 6. Local Filesystem Implementation

**Create: `breakthevibe/storage/local_store.py`**

```python
"""Local filesystem adapter implementing the ObjectStore interface."""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


class LocalObjectStore(ObjectStore):
    """Local filesystem storage. Keys map to file paths under base_dir."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._base / key

    async def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.debug("local_put", key=key, size=len(data))
        return key

    async def get(self, key: str) -> bytes | None:
        path = self._path(key)
        if not path.exists():
            return None
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def list_keys(self, prefix: str) -> list[str]:
        prefix_path = self._path(prefix)
        if not prefix_path.exists():
            return []
        base_str = str(self._base)
        return [
            str(f.relative_to(self._base))
            for f in prefix_path.rglob("*")
            if f.is_file()
        ]

    async def delete_prefix(self, prefix: str) -> int:
        prefix_path = self._path(prefix)
        if not prefix_path.exists():
            return 0
        keys = await self.list_keys(prefix)
        count = len(keys)
        shutil.rmtree(prefix_path)
        logger.info("local_prefix_deleted", prefix=prefix, count=count)
        return count

    async def get_usage_bytes(self, prefix: str) -> int:
        prefix_path = self._path(prefix)
        if not prefix_path.exists():
            return 0
        return sum(f.stat().st_size for f in prefix_path.rglob("*") if f.is_file())
```

---

## 7. Factory Function

**Add to: `breakthevibe/storage/object_store.py`** (or a separate factory file)

```python
def create_object_store() -> ObjectStore:
    """Create the appropriate ObjectStore based on settings."""
    from pathlib import Path
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if settings.use_s3:
        from breakthevibe.storage.s3_store import S3ObjectStore
        return S3ObjectStore(
            bucket=settings.s3_bucket or "",
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id or "",
            secret_access_key=settings.s3_secret_access_key or "",
            region=settings.s3_region,
        )
    from breakthevibe.storage.local_store import LocalObjectStore
    return LocalObjectStore(base_dir=Path(settings.artifacts_dir).expanduser())
```

---

## 8. Object Key Structure

All keys are prefixed with `tenants/{org_id}/` for data isolation:

```
tenants/{org_id}/projects/{project_id}/runs/{run_id}/
    screenshots/{step_name}.png
    videos/{video_name}.webm
    diffs/{diff_name}.png
    tests/{suite_name}.py
```

Example:
```
tenants/abc-123/projects/42/runs/run-uuid/screenshots/login_step1.png
```

---

## 9. ArtifactStore Refactor

**Modify: `breakthevibe/storage/artifacts.py`**

Refactor to use `ObjectStore` as backend:

```python
"""Artifact storage — wraps ObjectStore with tenant-scoped key building."""

from __future__ import annotations

import structlog

from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)

# Content type mapping
_CONTENT_TYPES = {
    ".png": "image/png",
    ".webm": "video/webm",
    ".jpg": "image/jpeg",
    ".py": "text/x-python",
}


class ArtifactStore:
    """Manages artifact storage with tenant-scoped key prefixes."""

    def __init__(self, store: ObjectStore, org_id: str) -> None:
        self._store = store
        self._org_id = org_id

    def _key(self, project_id: str, run_id: str, *parts: str) -> str:
        """Build a tenant-scoped object key."""
        segments = [
            "tenants", self._org_id,
            "projects", project_id,
            "runs", run_id,
            *parts,
        ]
        return "/".join(segments)

    async def save_screenshot(
        self, project_id: str, run_id: str, step_name: str, data: bytes
    ) -> str:
        key = self._key(project_id, run_id, "screenshots", f"{step_name}.png")
        await self._store.put(key, data, content_type="image/png")
        logger.debug("screenshot_saved", key=key, size=len(data))
        return key

    async def save_video(
        self, project_id: str, run_id: str, video_name: str, data: bytes
    ) -> str:
        key = self._key(project_id, run_id, "videos", f"{video_name}.webm")
        await self._store.put(key, data, content_type="video/webm")
        logger.debug("video_saved", key=key, size=len(data))
        return key

    async def get_screenshot(
        self, project_id: str, run_id: str, step_name: str
    ) -> bytes | None:
        key = self._key(project_id, run_id, "screenshots", f"{step_name}.png")
        return await self._store.get(key)

    async def list_screenshots(self, project_id: str, run_id: str) -> list[str]:
        prefix = self._key(project_id, run_id, "screenshots") + "/"
        return await self._store.list_keys(prefix)

    async def cleanup_run(self, project_id: str, run_id: str) -> int:
        prefix = self._key(project_id, run_id)
        count = await self._store.delete_prefix(prefix)
        logger.info("run_artifacts_cleaned", project=project_id,
                     run=run_id, count=count)
        return count

    async def cleanup_project(self, project_id: str) -> int:
        prefix = f"tenants/{self._org_id}/projects/{project_id}"
        count = await self._store.delete_prefix(prefix)
        logger.info("project_artifacts_cleaned", project=project_id, count=count)
        return count

    async def cleanup_tenant(self) -> int:
        """Delete ALL artifacts for this tenant (GDPR purge)."""
        prefix = f"tenants/{self._org_id}"
        count = await self._store.delete_prefix(prefix)
        logger.info("tenant_artifacts_cleaned", org_id=self._org_id, count=count)
        return count

    async def get_disk_usage(self, project_id: str | None = None) -> int:
        """Get total storage in bytes for a project or entire tenant."""
        if project_id:
            prefix = f"tenants/{self._org_id}/projects/{project_id}"
        else:
            prefix = f"tenants/{self._org_id}"
        return await self._store.get_usage_bytes(prefix)

    def get_run_dir(self, project_id: str, run_id: str) -> str:
        """Return the key prefix for a run directory (for test output)."""
        return self._key(project_id, run_id)
```

---

## 10. Pipeline Integration

**Modify: `breakthevibe/web/pipeline.py`**

Update `build_pipeline` to create a tenant-scoped `ArtifactStore`:

```python
def build_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    org_id: str = "",  # NEW
) -> PipelineOrchestrator:
    settings = get_settings()
    run_id = str(uuid.uuid4())

    # Object store (S3 or local)
    from breakthevibe.storage.object_store import create_object_store
    object_store = create_object_store()

    # Tenant-scoped artifact store
    artifacts = ArtifactStore(store=object_store, org_id=org_id or "default")

    # ... rest of pipeline build unchanged ...
```

---

## 11. GDPR: Tenant Artifact Purge

The `cleanup_tenant()` method on `ArtifactStore` deletes everything under `tenants/{org_id}/`. This is called by the tenant purge workflow (designed in the main plan):

```python
async def purge_tenant_artifacts(org_id: str) -> int:
    """Delete all artifacts for a tenant across S3/local storage."""
    object_store = create_object_store()
    artifact_store = ArtifactStore(store=object_store, org_id=org_id)
    return await artifact_store.cleanup_tenant()
```

---

## 12. Testing with MinIO (Local S3)

Add MinIO to `docker-compose.yml` for dev testing:

```yaml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"  # Console
    volumes:
      - minio_data:/data
    profiles:
      - s3

volumes:
  minio_data:
```

Test environment:
```bash
USE_S3=true
S3_BUCKET=breakthevibe-artifacts
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_REGION=us-east-1
```

Create the bucket:
```bash
aws --endpoint-url http://localhost:9000 s3 mb s3://breakthevibe-artifacts
```

---

## 13. Cloudflare R2 Configuration

For production with R2:

```bash
USE_S3=true
S3_BUCKET=breakthevibe-artifacts
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=<r2-access-key>
S3_SECRET_ACCESS_KEY=<r2-secret-key>
S3_REGION=auto
```

R2 is S3-compatible, so `S3ObjectStore` works without changes.

---

## 14. Verification Checklist

- [ ] `USE_S3=false` (default): local storage works as before
- [ ] `USE_S3=true` with MinIO: upload, download, list, delete work
- [ ] Object keys include `tenants/{org_id}/` prefix
- [ ] `cleanup_run` deletes all artifacts for a run
- [ ] `cleanup_project` deletes all artifacts for a project
- [ ] `cleanup_tenant` deletes all artifacts for the org (GDPR)
- [ ] `get_disk_usage` returns correct byte count
- [ ] Pipeline builds with S3 artifact store
- [ ] Screenshots saved during crawl are retrievable
- [ ] R2 endpoint works (S3-compatible)

---

## 15. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/storage/object_store.py` (~60 lines) |
| CREATE | `breakthevibe/storage/s3_store.py` (~120 lines) |
| CREATE | `breakthevibe/storage/local_store.py` (~80 lines) |
| MODIFY | `breakthevibe/storage/artifacts.py` (full rewrite ~100 lines) |
| MODIFY | `breakthevibe/config/settings.py` (S3 settings + validation) |
| MODIFY | `breakthevibe/web/pipeline.py` (tenant-scoped artifact store) |
| MODIFY | `pyproject.toml` (aiobotocore dependency) |
| MODIFY | `docker-compose.yml` (optional MinIO service) |
