"""Unit tests for LlmSettingsRepository (DB-backed with SQLite)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from breakthevibe.storage.repositories.llm_settings import _DEFAULTS, LlmSettingsRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.unit
class TestLlmSettingsRepositoryDefaults:
    async def test_get_all_returns_dict(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert isinstance(result, dict)

    async def test_get_all_contains_default_provider(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "default_provider" in result
        assert result["default_provider"] == "anthropic"

    async def test_get_all_contains_default_model(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "default_model" in result
        assert isinstance(result["default_model"], str)
        assert len(result["default_model"]) > 0

    async def test_get_all_contains_modules(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "modules" in result
        modules = result["modules"]
        assert isinstance(modules, dict)

    async def test_modules_contains_mapper(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "mapper" in result["modules"]

    async def test_modules_contains_generator(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "generator" in result["modules"]

    async def test_modules_contains_agent(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "agent" in result["modules"]

    async def test_get_all_contains_providers(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "providers" in result
        assert isinstance(result["providers"], dict)

    async def test_providers_contains_anthropic(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "anthropic" in result["providers"]

    async def test_providers_contains_openai(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "openai" in result["providers"]

    async def test_providers_contains_ollama(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        assert "ollama" in result["providers"]

    async def test_ollama_provider_has_base_url(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        ollama = result["providers"]["ollama"]
        assert "base_url" in ollama
        assert ollama["base_url"] == "http://localhost:11434"

    async def test_defaults_match_module_level_constant(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        result = await repo.get_all()
        for key, value in _DEFAULTS.items():
            assert result[key] == value


@pytest.mark.unit
class TestLlmSettingsRepositorySet:
    async def test_set_persists_new_key(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("custom_key", "custom_value")
        result = await repo.get_all()
        assert result["custom_key"] == "custom_value"

    async def test_set_overwrites_existing_key(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("default_provider", "openai")
        result = await repo.get_all()
        assert result["default_provider"] == "openai"

    async def test_set_with_dict_value(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        new_modules = {"mapper": {"provider": "openai", "model": "gpt-4o"}}
        await repo.set("modules", new_modules)
        result = await repo.get_all()
        assert result["modules"] == new_modules

    async def test_set_with_integer_value(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("max_tokens", 8192)
        result = await repo.get_all()
        assert result["max_tokens"] == 8192

    async def test_set_with_boolean_value(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("streaming_enabled", True)
        result = await repo.get_all()
        assert result["streaming_enabled"] is True

    async def test_set_with_none_value(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("optional_field", None)
        result = await repo.get_all()
        assert result["optional_field"] is None

    async def test_set_does_not_affect_other_keys(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        original_model = (await repo.get_all())["default_model"]
        await repo.set("default_provider", "ollama")
        result = await repo.get_all()
        assert result["default_model"] == original_model

    async def test_multiple_set_calls_accumulate(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("key_alpha", 1)
        await repo.set("key_beta", 2)
        result = await repo.get_all()
        assert result["key_alpha"] == 1
        assert result["key_beta"] == 2


@pytest.mark.unit
class TestLlmSettingsRepositorySetMany:
    async def test_set_many_persists_all_keys(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        updates = {"default_provider": "openai", "default_model": "gpt-4o"}
        await repo.set_many(updates)
        result = await repo.get_all()
        assert result["default_provider"] == "openai"
        assert result["default_model"] == "gpt-4o"

    async def test_set_many_with_empty_dict_is_noop(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        original = await repo.get_all()
        await repo.set_many({})
        result = await repo.get_all()
        assert result == original

    async def test_set_many_overwrites_existing_keys(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set_many({"default_provider": "ollama", "default_model": "llama3"})
        result = await repo.get_all()
        assert result["default_provider"] == "ollama"
        assert result["default_model"] == "llama3"

    async def test_set_many_with_mixed_value_types(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        updates = {
            "string_key": "hello",
            "int_key": 42,
            "bool_key": False,
            "list_key": [1, 2, 3],
            "dict_key": {"nested": True},
        }
        await repo.set_many(updates)
        result = await repo.get_all()
        for key, expected in updates.items():
            assert result[key] == expected

    async def test_set_many_does_not_affect_unrelated_keys(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        original_providers = (await repo.get_all())["providers"]
        await repo.set_many({"default_provider": "openai"})
        result = await repo.get_all()
        assert result["providers"] == original_providers

    async def test_set_many_after_set_retains_both(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("solo_key", "solo_value")
        await repo.set_many({"batch_key_a": 1, "batch_key_b": 2})
        result = await repo.get_all()
        assert result["solo_key"] == "solo_value"
        assert result["batch_key_a"] == 1
        assert result["batch_key_b"] == 2

    async def test_set_then_set_many_overwrites_same_key(self, async_engine: AsyncEngine) -> None:
        repo = LlmSettingsRepository(async_engine)
        await repo.set("shared_key", "first")
        await repo.set_many({"shared_key": "second"})
        result = await repo.get_all()
        assert result["shared_key"] == "second"
