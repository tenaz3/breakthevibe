"""Unit tests for InMemoryLlmSettingsRepository."""

from __future__ import annotations

import pytest

from breakthevibe.storage.repositories.llm_settings import (
    _DEFAULTS,
    InMemoryLlmSettingsRepository,
)


@pytest.mark.unit
class TestInMemoryLlmSettingsRepositoryDefaults:
    @pytest.mark.asyncio
    async def test_get_all_returns_dict(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_all_contains_default_provider(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "default_provider" in result
        assert result["default_provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_get_all_contains_default_model(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "default_model" in result
        assert isinstance(result["default_model"], str)
        assert len(result["default_model"]) > 0

    @pytest.mark.asyncio
    async def test_get_all_contains_modules(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "modules" in result
        modules = result["modules"]
        assert isinstance(modules, dict)

    @pytest.mark.asyncio
    async def test_modules_contains_mapper(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "mapper" in result["modules"]

    @pytest.mark.asyncio
    async def test_modules_contains_generator(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "generator" in result["modules"]

    @pytest.mark.asyncio
    async def test_modules_contains_agent(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "agent" in result["modules"]

    @pytest.mark.asyncio
    async def test_get_all_contains_providers(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "providers" in result
        assert isinstance(result["providers"], dict)

    @pytest.mark.asyncio
    async def test_providers_contains_anthropic(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "anthropic" in result["providers"]

    @pytest.mark.asyncio
    async def test_providers_contains_openai(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "openai" in result["providers"]

    @pytest.mark.asyncio
    async def test_providers_contains_ollama(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        assert "ollama" in result["providers"]

    @pytest.mark.asyncio
    async def test_ollama_provider_has_base_url(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        ollama = result["providers"]["ollama"]
        assert "base_url" in ollama
        assert ollama["base_url"] == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_get_all_returns_copy_not_internal_reference(self) -> None:
        """Mutating the returned dict must not affect internal state."""
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        result["injected_key"] = "injected_value"
        fresh = await repo.get_all()
        assert "injected_key" not in fresh

    @pytest.mark.asyncio
    async def test_defaults_match_module_level_constant(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        result = await repo.get_all()
        for key, value in _DEFAULTS.items():
            assert result[key] == value


@pytest.mark.unit
class TestInMemoryLlmSettingsRepositorySet:
    @pytest.mark.asyncio
    async def test_set_persists_new_key(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("custom_key", "custom_value")
        result = await repo.get_all()
        assert result["custom_key"] == "custom_value"

    @pytest.mark.asyncio
    async def test_set_overwrites_existing_key(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("default_provider", "openai")
        result = await repo.get_all()
        assert result["default_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_set_with_dict_value(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        new_modules = {"mapper": {"provider": "openai", "model": "gpt-4o"}}
        await repo.set("modules", new_modules)
        result = await repo.get_all()
        assert result["modules"] == new_modules

    @pytest.mark.asyncio
    async def test_set_with_integer_value(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("max_tokens", 8192)
        result = await repo.get_all()
        assert result["max_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_set_with_boolean_value(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("streaming_enabled", True)
        result = await repo.get_all()
        assert result["streaming_enabled"] is True

    @pytest.mark.asyncio
    async def test_set_with_none_value(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("optional_field", None)
        result = await repo.get_all()
        assert result["optional_field"] is None

    @pytest.mark.asyncio
    async def test_set_does_not_affect_other_keys(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        original_model = (await repo.get_all())["default_model"]
        await repo.set("default_provider", "ollama")
        result = await repo.get_all()
        assert result["default_model"] == original_model

    @pytest.mark.asyncio
    async def test_set_is_not_reflected_across_instances(self) -> None:
        """Each InMemoryLlmSettingsRepository instance has isolated state."""
        repo_a = InMemoryLlmSettingsRepository()
        repo_b = InMemoryLlmSettingsRepository()
        await repo_a.set("default_provider", "openai")
        result_b = await repo_b.get_all()
        # repo_b should still have the default value
        assert result_b["default_provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_multiple_set_calls_accumulate(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("key_alpha", 1)
        await repo.set("key_beta", 2)
        result = await repo.get_all()
        assert result["key_alpha"] == 1
        assert result["key_beta"] == 2


@pytest.mark.unit
class TestInMemoryLlmSettingsRepositorySetMany:
    @pytest.mark.asyncio
    async def test_set_many_persists_all_keys(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        updates = {"default_provider": "openai", "default_model": "gpt-4o"}
        await repo.set_many(updates)
        result = await repo.get_all()
        assert result["default_provider"] == "openai"
        assert result["default_model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_set_many_with_empty_dict_is_noop(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        original = await repo.get_all()
        await repo.set_many({})
        result = await repo.get_all()
        assert result == original

    @pytest.mark.asyncio
    async def test_set_many_overwrites_existing_keys(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set_many({"default_provider": "ollama", "default_model": "llama3"})
        result = await repo.get_all()
        assert result["default_provider"] == "ollama"
        assert result["default_model"] == "llama3"

    @pytest.mark.asyncio
    async def test_set_many_with_mixed_value_types(self) -> None:
        repo = InMemoryLlmSettingsRepository()
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

    @pytest.mark.asyncio
    async def test_set_many_does_not_affect_unrelated_keys(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        original_providers = (await repo.get_all())["providers"]
        await repo.set_many({"default_provider": "openai"})
        result = await repo.get_all()
        assert result["providers"] == original_providers

    @pytest.mark.asyncio
    async def test_set_many_after_set_retains_both(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("solo_key", "solo_value")
        await repo.set_many({"batch_key_a": 1, "batch_key_b": 2})
        result = await repo.get_all()
        assert result["solo_key"] == "solo_value"
        assert result["batch_key_a"] == 1
        assert result["batch_key_b"] == 2

    @pytest.mark.asyncio
    async def test_set_then_set_many_overwrites_same_key(self) -> None:
        repo = InMemoryLlmSettingsRepository()
        await repo.set("shared_key", "first")
        await repo.set_many({"shared_key": "second"})
        result = await repo.get_all()
        assert result["shared_key"] == "second"
