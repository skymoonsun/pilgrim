"""Abstract LLM provider interface and factory.

New providers are added by:
1. Creating a new subclass of ``LLMProvider``.
2. Adding an ``elif`` branch in ``create_llm_provider()``.
3. Adding config settings for the provider in ``app.core.config``.

No service or API code needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AIDisabledError


class LLMProvider(ABC):
    """Abstract base for LLM providers.

    Subclasses must implement ``generate`` and ``close``.
    """

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> BaseModel | str:
        """Send a prompt and return structured or raw text output.

        If *schema* is provided, the provider must request structured
        output conforming to that Pydantic model and return a validated
        instance.  Otherwise, return raw text.

        If *system* is provided, it is sent as the system message
        (or equivalent) to steer model behavior.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release resources (HTTP clients, etc.)."""


def create_llm_provider() -> LLMProvider:
    """Instantiate the configured LLM provider from app settings."""
    settings = get_settings()
    if not settings.ai_enabled:
        raise AIDisabledError()

    provider: str = settings.llm_provider

    if provider == "ollama":
        from app.integrations.ollama_client import OllamaProvider

        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            token=settings.ollama_token,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")