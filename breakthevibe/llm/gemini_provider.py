"""Google Gemini LLM provider implementation."""

from __future__ import annotations

from google import genai
from google.genai import types

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


class GeminiProvider(LLMProviderBase):
    """Google Gemini provider via the google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a text response from Gemini."""
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
        )
        if system:
            config.system_instruction = system

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            raise LLMProviderError(f"Gemini API error: {e}") from e

        usage = response.usage_metadata
        tokens_used = 0
        if usage:
            tokens_used = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)

        return LLMResponse(
            content=response.text or "",
            model=self._model,
            tokens_used=tokens_used,
        )

    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a structured (JSON) response from Gemini."""
        system_with_json = (
            system or ""
        ) + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        return await self.generate(prompt, system=system_with_json.strip(), max_tokens=max_tokens)
