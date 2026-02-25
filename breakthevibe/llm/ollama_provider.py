"""Ollama (local model) LLM provider implementation."""

from __future__ import annotations

from typing import Any

import httpx

from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


class OllamaProvider(LLMProviderBase):
    """Ollama local model provider using its HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a text response from Ollama."""
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return LLMResponse(
            content=data.get("response", ""),
            model=self._model,
            tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
        )

    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a structured (JSON) response from Ollama."""
        system_with_json = (
            system or ""
        ) + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        return await self.generate(prompt, system=system_with_json.strip(), max_tokens=max_tokens)
