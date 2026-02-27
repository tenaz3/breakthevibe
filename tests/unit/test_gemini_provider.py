"""Unit tests for GeminiProvider in breakthevibe/llm/gemini_provider.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.gemini_provider import GeminiProvider
from breakthevibe.llm.provider import LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(
    text: str = "Hello from Gemini",
    prompt_tokens: int = 10,
    candidates_tokens: int = 5,
) -> MagicMock:
    """Build a MagicMock that mimics a Gemini GenerateContentResponse."""
    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidates_tokens

    response = MagicMock()
    response.text = text
    response.usage_metadata = usage
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeminiProviderGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate("Say hello")

        assert isinstance(result, LLMResponse)

    @pytest.mark.asyncio
    async def test_generate_content_matches_response(self) -> None:
        mock_response = _make_mock_response(text="Gemini says hi")

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate("Hi")

        assert result.content == "Gemini says hi"

    @pytest.mark.asyncio
    async def test_generate_model_name_matches_configured(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key", model="gemini-2.5-pro")
            result = await provider.generate("Hi")

        assert result.model == "gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_generate_tokens_used_is_sum(self) -> None:
        mock_response = _make_mock_response(prompt_tokens=20, candidates_tokens=8)

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate("Prompt")

        assert result.tokens_used == 28

    @pytest.mark.asyncio
    async def test_generate_without_usage_returns_zero_tokens(self) -> None:
        mock_response = _make_mock_response()
        mock_response.usage_metadata = None

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate("Prompt")

        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_passes_model_to_api(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash-lite")
            await provider.generate("Test")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            assert call_kwargs["model"] == "gemini-2.5-flash-lite"

    @pytest.mark.asyncio
    async def test_generate_passes_system_instruction(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            await provider.generate("Question", system="You are a QA expert")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            config = call_kwargs["config"]
            assert config.system_instruction == "You are a QA expert"

    @pytest.mark.asyncio
    async def test_generate_without_system_has_no_system_instruction(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            await provider.generate("Prompt without system")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            config = call_kwargs["config"]
            assert not hasattr(config, "system_instruction") or config.system_instruction is None

    @pytest.mark.asyncio
    async def test_generate_empty_text_returns_empty_string(self) -> None:
        mock_response = _make_mock_response(text="")
        mock_response.text = None

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate("Test")

        assert result.content == ""

    @pytest.mark.asyncio
    async def test_generate_default_model_is_gemini_flash(self) -> None:
        mock_response = _make_mock_response()

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            await provider.generate("Test")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            assert call_kwargs["model"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_client_initialised_with_api_key(self) -> None:
        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=_make_mock_response())
            mock_genai.Client.return_value = mock_client

            GeminiProvider(api_key="my-secret-key")

        mock_genai.Client.assert_called_once_with(api_key="my-secret-key")

    @pytest.mark.asyncio
    async def test_generate_api_error_raises_llm_provider_error(self) -> None:
        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                side_effect=RuntimeError("API down")
            )
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            with pytest.raises(LLMProviderError, match="Gemini API error"):
                await provider.generate("Test")


@pytest.mark.unit
class TestGeminiProviderGenerateStructured:
    @pytest.mark.asyncio
    async def test_generate_structured_returns_llm_response(self) -> None:
        mock_response = _make_mock_response(text='{"result": "ok"}')

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            result = await provider.generate_structured("Return JSON")

        assert isinstance(result, LLMResponse)
        assert result.content == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_generate_structured_uses_json_mime_type(self) -> None:
        mock_response = _make_mock_response(text="{}")

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            await provider.generate_structured("Return JSON", system="Be concise")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            config = call_kwargs["config"]
            assert config.response_mime_type == "application/json"
            assert config.system_instruction == "Be concise"

    @pytest.mark.asyncio
    async def test_generate_structured_without_system_omits_instruction(self) -> None:
        mock_response = _make_mock_response(text="{}")

        with patch("breakthevibe.llm.gemini_provider.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            provider = GeminiProvider(api_key="test-key")
            await provider.generate_structured("Return JSON")

            call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
            config = call_kwargs["config"]
            assert config.response_mime_type == "application/json"
            assert not hasattr(config, "system_instruction") or config.system_instruction is None
