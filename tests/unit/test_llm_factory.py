from unittest.mock import patch

import pytest

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.factory import create_llm_provider
from breakthevibe.llm.gemini_provider import GeminiProvider
from breakthevibe.types import LLMProvider


@pytest.mark.unit
class TestLLMFactory:
    def test_create_anthropic_provider(self) -> None:
        provider = create_llm_provider(LLMProvider.ANTHROPIC, api_key="test-key")
        assert isinstance(provider, AnthropicProvider)

    def test_create_gemini_provider(self) -> None:
        with patch("breakthevibe.llm.gemini_provider.genai"):
            provider = create_llm_provider(LLMProvider.GEMINI, api_key="test-key")
        assert isinstance(provider, GeminiProvider)

    def test_create_gemini_without_api_key_raises(self) -> None:
        with pytest.raises(LLMProviderError, match="API key"):
            create_llm_provider(LLMProvider.GEMINI, api_key=None)

    def test_create_unknown_provider_raises(self) -> None:
        with pytest.raises(LLMProviderError, match="Unsupported"):
            create_llm_provider("unknown", api_key="test")  # type: ignore[arg-type]

    def test_create_without_api_key_raises(self) -> None:
        with pytest.raises(LLMProviderError, match="API key"):
            create_llm_provider(LLMProvider.ANTHROPIC, api_key=None)
