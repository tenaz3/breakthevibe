"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int


class LLMProviderBase(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def generate(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a text response from the LLM."""

    @abstractmethod
    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a structured (JSON) response from the LLM."""
