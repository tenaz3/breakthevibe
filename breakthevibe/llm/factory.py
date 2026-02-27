"""Factory for creating LLM provider instances."""

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.gemini_provider import GeminiProvider
from breakthevibe.llm.ollama_provider import OllamaProvider
from breakthevibe.llm.openai_provider import OpenAIProvider
from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.types import LLMProvider


def create_llm_provider(
    provider: LLMProvider | str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMProviderBase:
    """Create an LLM provider instance."""
    provider_str = str(provider)

    if provider_str == LLMProvider.ANTHROPIC:
        if not api_key:
            raise LLMProviderError("API key required for Anthropic provider")
        return AnthropicProvider(api_key=api_key, **({"model": model} if model else {}))
    elif provider_str == LLMProvider.OPENAI:
        if not api_key:
            raise LLMProviderError("API key required for OpenAI provider")
        return OpenAIProvider(api_key=api_key, **({"model": model} if model else {}))
    elif provider_str == LLMProvider.GEMINI:
        if not api_key:
            raise LLMProviderError("API key required for Gemini provider")
        return GeminiProvider(api_key=api_key, **({"model": model} if model else {}))
    elif provider_str == LLMProvider.OLLAMA:
        kwargs: dict[str, str] = {}
        if model:
            kwargs["model"] = model
        if base_url:
            kwargs["base_url"] = base_url
        return OllamaProvider(**kwargs)
    else:
        raise LLMProviderError(f"Unsupported LLM provider: {provider}")
