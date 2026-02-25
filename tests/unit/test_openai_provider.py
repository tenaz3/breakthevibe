"""Unit tests for OpenAIProvider in breakthevibe/llm/openai_provider.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.llm.openai_provider import OpenAIProvider
from breakthevibe.llm.provider import LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    content: str = "Hello from GPT",
    model: str = "gpt-4o",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a MagicMock that mimics an OpenAI ChatCompletion response object."""
    choice = MagicMock()
    choice.message.content = content

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenAIProviderGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate("Say hello")

        assert isinstance(result, LLMResponse)

    @pytest.mark.asyncio
    async def test_generate_content_matches_response(self) -> None:
        mock_response = _make_mock_response(content="GPT says hi")

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate("Hi")

        assert result.content == "GPT says hi"

    @pytest.mark.asyncio
    async def test_generate_model_name_matches_response(self) -> None:
        mock_response = _make_mock_response(model="gpt-4o-mini")

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
            result = await provider.generate("Hi")

        assert result.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_generate_tokens_used_is_sum_of_prompt_and_completion(self) -> None:
        mock_response = _make_mock_response(prompt_tokens=20, completion_tokens=8)

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate("Prompt")

        assert result.tokens_used == 28

    @pytest.mark.asyncio
    async def test_generate_without_usage_returns_zero_tokens(self) -> None:
        mock_response = _make_mock_response()
        mock_response.usage = None

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate("Prompt")

        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_sends_user_message(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("my prompt")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            user_messages = [m for m in messages if m["role"] == "user"]
            assert len(user_messages) == 1
            assert user_messages[0]["content"] == "my prompt"

    @pytest.mark.asyncio
    async def test_generate_without_system_has_no_system_message(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("Prompt without system")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            system_messages = [m for m in messages if m["role"] == "system"]
            assert len(system_messages) == 0

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt_included(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("Question", system="You are a QA expert")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            system_messages = [m for m in messages if m["role"] == "system"]
            assert len(system_messages) == 1
            assert system_messages[0]["content"] == "You are a QA expert"

    @pytest.mark.asyncio
    async def test_generate_system_message_comes_before_user(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("Q", system="System instruction")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_generate_passes_model_to_api(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test", model="gpt-3.5-turbo")
            await provider.generate("Test")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_generate_passes_max_tokens_to_api(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("Test", max_tokens=1024)

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_generate_empty_content_returns_empty_string(self) -> None:
        mock_response = _make_mock_response(content="")
        mock_response.choices[0].message.content = None  # API can return None

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate("Test")

        assert result.content == ""

    @pytest.mark.asyncio
    async def test_generate_default_model_is_gpt4o(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate("Test")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_client_initialised_with_api_key(self) -> None:
        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_response())
            mock_cls.return_value = mock_client

            OpenAIProvider(api_key="sk-secret-key")

        mock_cls.assert_called_once_with(api_key="sk-secret-key")


@pytest.mark.unit
class TestOpenAIProviderGenerateStructured:
    @pytest.mark.asyncio
    async def test_generate_structured_returns_llm_response(self) -> None:
        mock_response = _make_mock_response(content='{"result": "ok"}')

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            result = await provider.generate_structured("Return JSON")

        assert isinstance(result, LLMResponse)
        assert result.content == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_generate_structured_appends_json_instruction_to_system(self) -> None:
        mock_response = _make_mock_response(content="{}")

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate_structured("Return JSON", system="Be concise")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            system_messages = [m for m in messages if m["role"] == "system"]
            assert len(system_messages) == 1
            assert "JSON" in system_messages[0]["content"]
            assert "Be concise" in system_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_generate_structured_without_system_adds_json_instruction(self) -> None:
        mock_response = _make_mock_response(content="{}")

        with patch("breakthevibe.llm.openai_provider.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            provider = OpenAIProvider(api_key="sk-test")
            await provider.generate_structured("Return JSON")

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            system_messages = [m for m in messages if m["role"] == "system"]
            assert len(system_messages) == 1
            assert "JSON" in system_messages[0]["content"]
