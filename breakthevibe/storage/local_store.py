"""Local filesystem object store implementation."""

from __future__ import annotations

import asyncio
import pathlib  # noqa: TC003 - used at runtime for Path operations
import shutil

import structlog

from breakthevibe.storage.object_store import ObjectStore

logger = structlog.get_logger(__name__)


class LocalObjectStore(ObjectStore):
    """Object store backed by local filesystem with path traversal protection."""

    def __init__(self, base_dir: pathlib.Path) -> None:
        self._base = base_dir.resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> pathlib.Path:
        """Resolve key to absolute path with traversal protection (C-7)."""
        path = (self._base / key).resolve()
        if not str(path).startswith(str(self._base)):
            msg = f"Path traversal detected: {key}"
            raise ValueError(msg)
        return path

    async def put(self, key: str, data: bytes) -> None:
        """Write data to local file."""
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        logger.debug("local_store_put", key=key, size=len(data))

    async def get(self, key: str) -> bytes | None:
        """Read data from local file."""
        path = self._resolve_path(key)
        if not path.exists():
            return None
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        """Delete a file or directory tree."""
        path = self._resolve_path(key)
        if path.is_dir():
            await asyncio.to_thread(shutil.rmtree, path)
        elif path.exists():
            await asyncio.to_thread(path.unlink)

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all file keys under a prefix."""
        base = self._resolve_path(prefix) if prefix else self._base
        if not base.exists():
            return []

        def _list() -> list[str]:
            return sorted(str(f.relative_to(self._base)) for f in base.rglob("*") if f.is_file())

        return await asyncio.to_thread(_list)

    async def get_usage_bytes(self, prefix: str = "") -> int:
        """Get total disk usage for keys under prefix."""
        base = self._resolve_path(prefix) if prefix else self._base
        if not base.exists():
            return 0

        def _usage() -> int:
            return sum(f.stat().st_size for f in base.rglob("*") if f.is_file())

        return await asyncio.to_thread(_usage)
