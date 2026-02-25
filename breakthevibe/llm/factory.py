"""Factory for creating LLM provider instances."""

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.types import LLMProvider


def create_llm_provider(
    provider: LLMProvider,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMProviderBase:
    """Create an LLM provider instance."""
    if provider == LLMProvider.ANTHROPIC:
        if not api_key:
            raise LLMProviderError("API key required for Anthropic provider")
        return AnthropicProvider(api_key=api_key, **({"model": model} if model else {}))
    elif provider == LLMProvider.OPENAI:
        if not api_key:
            raise LLMProviderError("API key required for OpenAI provider")
        raise LLMProviderError("OpenAI provider not yet implemented")
    elif provider == LLMProvider.OLLAMA:
        raise LLMProviderError("Ollama provider not yet implemented")
    else:
        raise LLMProviderError(f"Unsupported LLM provider: {provider}")
