"""OpenAI LLM provider implementation."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


class OpenAIProvider(LLMProviderBase):
    """OpenAI GPT provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a text response from OpenAI."""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_used=(usage.prompt_tokens + usage.completion_tokens) if usage else 0,
        )

    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a structured (JSON) response from OpenAI."""
        system_with_json = (
            system or ""
        ) + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        return await self.generate(prompt, system=system_with_json.strip(), max_tokens=max_tokens)
