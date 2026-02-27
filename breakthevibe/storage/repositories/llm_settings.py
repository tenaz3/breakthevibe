"""LLM settings repository — in-memory with DB-backed persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import LlmSetting

logger = structlog.get_logger(__name__)

# Default settings used when no persisted settings exist
_DEFAULTS: dict[str, Any] = {
    "default_provider": "anthropic",
    "default_model": "claude-sonnet-4-20250514",
    "modules": {
        "mapper": {"provider": "", "model": ""},
        "generator": {"provider": "", "model": ""},
        "agent": {"provider": "", "model": ""},
    },
    "providers": {
        "anthropic": {"api_key": ""},
        "openai": {"api_key": ""},
        "gemini": {"api_key": ""},
        "ollama": {"base_url": "http://localhost:11434"},
    },
}


class LlmSettingsRepository:
    """Stores LLM settings in PostgreSQL via the LlmSetting model."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_all(self, org_id: str = SENTINEL_ORG_ID) -> dict[str, Any]:
        """Load all LLM settings for an org, falling back to defaults."""
        async with AsyncSession(self._engine) as session:
            statement = select(LlmSetting).where(col(LlmSetting.org_id) == org_id)
            results = await session.execute(statement)
            rows = results.scalars().all()

        settings = _DEFAULTS.copy()
        for row in rows:
            settings[row.key] = json.loads(row.value_json)
        return settings

    async def set(self, key: str, value: Any, org_id: str = SENTINEL_ORG_ID) -> None:
        """Persist a single setting key for an org."""
        async with AsyncSession(self._engine) as session:
            statement = select(LlmSetting).where(
                LlmSetting.key == key, col(LlmSetting.org_id) == org_id
            )
            results = await session.execute(statement)
            existing = results.scalars().first()
            if existing:
                existing.value_json = json.dumps(value)
                session.add(existing)
            else:
                session.add(LlmSetting(key=key, value_json=json.dumps(value), org_id=org_id))
            await session.commit()
            logger.debug("llm_setting_saved", key=key, org_id=org_id)

    async def set_many(self, updates: dict[str, Any], org_id: str = SENTINEL_ORG_ID) -> None:
        """Persist multiple settings at once for an org."""
        for key, value in updates.items():
            await self.set(key, value, org_id=org_id)


class InMemoryLlmSettingsRepository:
    """In-memory fallback for dev/testing without a database."""

    def __init__(self) -> None:
        self._settings: dict[str, dict[str, Any]] = {SENTINEL_ORG_ID: _DEFAULTS.copy()}

    async def get_all(self, org_id: str = SENTINEL_ORG_ID) -> dict[str, Any]:
        return self._settings.get(org_id, _DEFAULTS).copy()

    async def set(self, key: str, value: Any, org_id: str = SENTINEL_ORG_ID) -> None:
        self._settings.setdefault(org_id, _DEFAULTS.copy())[key] = value

    async def set_many(self, updates: dict[str, Any], org_id: str = SENTINEL_ORG_ID) -> None:
        self._settings.setdefault(org_id, _DEFAULTS.copy()).update(updates)
