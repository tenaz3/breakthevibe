"""Anthropic (Claude) LLM provider implementation."""

from typing import Any

from anthropic import AsyncAnthropic

from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


class AnthropicProvider(LLMProviderBase):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = await self._client.messages.create(**kwargs)
        return LLMResponse(
            content=message.content[0].text,
            model=message.model,
            tokens_used=message.usage.input_tokens + message.usage.output_tokens,
        )

    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        system_with_json = (
            (system or "") + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        )
        return await self.generate(
            prompt, system=system_with_json.strip(), max_tokens=max_tokens
        )
