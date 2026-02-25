"""Unit tests for OllamaProvider in breakthevibe/llm/ollama_provider.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.llm.ollama_provider import OllamaProvider
from breakthevibe.llm.provider import LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_httpx_response(
    response_text: str = "Ollama reply",
    eval_count: int = 12,
    prompt_eval_count: int = 8,
    raise_for_status: bool = False,
) -> MagicMock:
    """Build a MagicMock that mimics an httpx.Response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": response_text,
        "eval_count": eval_count,
        "prompt_eval_count": prompt_eval_count,
        "model": "llama3",
        "done": True,
    }
    if raise_for_status:
        mock_resp.raise_for_status.side_effect = Exception("HTTP error")
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


def _patch_httpx_client(mock_response: MagicMock) -> patch:
    """Patch httpx.AsyncClient so that POST returns mock_response."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("breakthevibe.llm.ollama_provider.httpx.AsyncClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOllamaProviderConstructor:
    def test_default_base_url(self) -> None:
        provider = OllamaProvider()
        assert provider._base_url == "http://localhost:11434"

    def test_trailing_slash_stripped_from_base_url(self) -> None:
        provider = OllamaProvider(base_url="http://localhost:11434/")
        assert provider._base_url == "http://localhost:11434"

    def test_custom_base_url(self) -> None:
        provider = OllamaProvider(base_url="http://ollama-server:11434")
        assert provider._base_url == "http://ollama-server:11434"

    def test_default_model(self) -> None:
        provider = OllamaProvider()
        assert provider._model == "llama3"

    def test_custom_model(self) -> None:
        provider = OllamaProvider(model="mistral")
        assert provider._model == "mistral"


@pytest.mark.unit
class TestOllamaProviderGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self) -> None:
        mock_resp = _make_mock_httpx_response()
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate("Hello Ollama")
        assert isinstance(result, LLMResponse)

    @pytest.mark.asyncio
    async def test_generate_content_from_response_field(self) -> None:
        mock_resp = _make_mock_httpx_response(response_text="Local model answer")
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate("Question")
        assert result.content == "Local model answer"

    @pytest.mark.asyncio
    async def test_generate_model_set_correctly(self) -> None:
        mock_resp = _make_mock_httpx_response()
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider(model="gemma")
            result = await provider.generate("Prompt")
        assert result.model == "gemma"

    @pytest.mark.asyncio
    async def test_generate_tokens_used_is_sum_of_eval_counts(self) -> None:
        mock_resp = _make_mock_httpx_response(eval_count=30, prompt_eval_count=15)
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate("Prompt")
        assert result.tokens_used == 45

    @pytest.mark.asyncio
    async def test_generate_tokens_zero_when_counts_absent(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "answer"}
        mock_resp.raise_for_status.return_value = None
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate("Prompt")
        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_posts_to_correct_url(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider(base_url="http://localhost:11434", model="llama3")
            await provider.generate("Test prompt")

        mock_client.post.assert_awaited_once()
        called_url = mock_client.post.call_args.args[0]
        assert called_url == "http://localhost:11434/api/generate"

    @pytest.mark.asyncio
    async def test_generate_sends_correct_model_in_payload(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider(model="mistral")
            await provider.generate("Prompt")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["model"] == "mistral"

    @pytest.mark.asyncio
    async def test_generate_sends_prompt_in_payload(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate("My specific question")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["prompt"] == "My specific question"

    @pytest.mark.asyncio
    async def test_generate_stream_is_false(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate("Test")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_generate_passes_num_predict_in_options(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate("Test", max_tokens=512)

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["options"]["num_predict"] == 512

    @pytest.mark.asyncio
    async def test_generate_without_system_excludes_system_key(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate("Prompt no system")

        payload = mock_client.post.call_args.kwargs["json"]
        assert "system" not in payload

    @pytest.mark.asyncio
    async def test_generate_with_system_includes_system_key(self) -> None:
        mock_resp = _make_mock_httpx_response()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate("Prompt", system="System directive")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["system"] == "System directive"

    @pytest.mark.asyncio
    async def test_generate_calls_raise_for_status(self) -> None:
        mock_resp = _make_mock_httpx_response()
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            await provider.generate("Prompt")
        mock_resp.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_propagates_http_error(self) -> None:
        import httpx

        from breakthevibe.exceptions import LLMProviderError

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=MagicMock(),
        )
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            with pytest.raises(LLMProviderError, match="Ollama API error"):
                await provider.generate("Prompt")

    @pytest.mark.asyncio
    async def test_generate_empty_response_returns_empty_content(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": "",
            "eval_count": 0,
            "prompt_eval_count": 0,
        }
        mock_resp.raise_for_status.return_value = None
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate("Prompt")
        assert result.content == ""


@pytest.mark.unit
class TestOllamaProviderGenerateStructured:
    @pytest.mark.asyncio
    async def test_generate_structured_returns_llm_response(self) -> None:
        mock_resp = _make_mock_httpx_response(response_text='{"key": "val"}')
        with _patch_httpx_client(mock_resp):
            provider = OllamaProvider()
            result = await provider.generate_structured("Give JSON")
        assert isinstance(result, LLMResponse)
        assert result.content == '{"key": "val"}'

    @pytest.mark.asyncio
    async def test_generate_structured_adds_json_instruction_to_system(self) -> None:
        mock_resp = _make_mock_httpx_response(response_text="{}")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate_structured("Return JSON", system="Be concise")

        payload = mock_client.post.call_args.kwargs["json"]
        assert "system" in payload
        assert "JSON" in payload["system"]
        assert "Be concise" in payload["system"]

    @pytest.mark.asyncio
    async def test_generate_structured_without_system_adds_json_instruction(self) -> None:
        mock_resp = _make_mock_httpx_response(response_text="{}")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "breakthevibe.llm.ollama_provider.httpx.AsyncClient",
            return_value=mock_client,
        ):
            provider = OllamaProvider()
            await provider.generate_structured("Give me JSON")

        payload = mock_client.post.call_args.kwargs["json"]
        assert "system" in payload
        assert "JSON" in payload["system"]
