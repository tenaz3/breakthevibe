from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.provider import LLMResponse


@pytest.mark.unit
class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_generate_calls_api(self) -> None:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Test response")]
        mock_message.model = "claude-sonnet-4-20250514"
        mock_message.usage.input_tokens = 10
        mock_message.usage.output_tokens = 5

        with patch("breakthevibe.llm.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="test-key")
            result = await provider.generate("Hello")

            assert isinstance(result, LLMResponse)
            assert result.content == "Test response"
            assert result.tokens_used == 15

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self) -> None:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Response")]
        mock_message.model = "claude-sonnet-4-20250514"
        mock_message.usage.input_tokens = 20
        mock_message.usage.output_tokens = 10

        with patch("breakthevibe.llm.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="test-key")
            result = await provider.generate("Hello", system="You are a tester")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["system"] == "You are a tester"
            assert result.content == "Response"

    @pytest.mark.asyncio
    async def test_generate_structured_adds_json_instruction(self) -> None:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"key": "value"}')]
        mock_message.model = "claude-sonnet-4-20250514"
        mock_message.usage.input_tokens = 15
        mock_message.usage.output_tokens = 8

        with patch("breakthevibe.llm.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(api_key="test-key")
            result = await provider.generate_structured("Return JSON")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert "JSON" in call_kwargs["system"]
            assert result.content == '{"key": "value"}'
