"""OpenAI-compatible LLM provider via plain HTTP (``httpx``).

Works against any ``/v1`` style endpoint: the manifold gateway, OpenAI,
vLLM, LM Studio, Ollama's OpenAI shim, ...  No SDK dependency — the same
approach the Ollama provider takes.

Configuration (environment):
- ``LLM_BASE_URL`` — API root, e.g. ``https://manifold.gokaygunes.com/gateway/v1``
- ``LLM_API_KEY``  — bearer token sent as ``Authorization: Bearer ...``
  (empty key ⇒ header omitted, for key-less local endpoints)
- ``LLM_MODEL``    — model/group name to request
- ``PILGRIM_LLM_PROVIDER=openai-compatible`` selects this provider.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.exceptions import AIConnectionError, AILLMError
from app.integrations.llm_base import LLMProvider
from app.integrations.ollama_client import _extract_json

logger = logging.getLogger(__name__)

_CHAT_COMPLETIONS_ENDPOINT = "/chat/completions"

# LLM calls can take a long while on big prompts (matches Ollama provider).
_HTTP_TIMEOUT_SECONDS = 600.0


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider speaking the OpenAI ``chat/completions`` dialect."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Key-less endpoints (LM Studio, Ollama shim) omit the header.
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=_HTTP_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def generate(
        self,
        *,
        prompt: str,
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> BaseModel | str:
        model_name = model or self._model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        }
        if schema is not None:
            # JSON mode keeps the model from wrapping the object in prose.
            # The schema itself rides along in the prompt (see ai_prompts).
            payload["response_format"] = {"type": "json_object"}
            payload["messages"] = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Return ONLY JSON conforming to this schema:\n"
                        f"{schema.model_json_schema()}"
                    ),
                },
            ]

        try:
            resp = await self._client.post(_CHAT_COMPLETIONS_ENDPOINT, json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise AIConnectionError("openai-compatible", self._base_url) from exc
        except httpx.TimeoutException as exc:
            raise AILLMError(
                "openai-compatible", f"Request timed out: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AILLMError(
                "openai-compatible",
                f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIConnectionError("openai-compatible", self._base_url) from exc

        try:
            body = resp.json()
            text: str = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AILLMError(
                "openai-compatible",
                f"Unexpected response shape: {exc}",
            ) from exc

        if schema is not None:
            extracted = _extract_json(text)
            try:
                return schema.model_validate_json(extracted)
            except Exception as exc:
                logger.warning(
                    "LLM response could not be parsed as %s. "
                    "Raw response (first 500 chars): %s",
                    schema.__name__,
                    text[:500],
                )
                raise AILLMError(
                    "openai-compatible",
                    f"Failed to parse structured output: {exc}",
                ) from exc

        return text

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
