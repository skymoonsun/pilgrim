"""Ollama LLM provider implementation.

Talks directly to the Ollama HTTP API (``POST /api/generate``) via
``httpx`` — no SDK dependency required.  Works with both local and
remote (external) Ollama instances; the base URL and optional bearer
token are configured via environment variables.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.exceptions import AIConnectionError, AILLMError
from app.integrations.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_GENERATE_ENDPOINT = "/api/generate"

# Matches ```json ... ``` or ``` ... ``` fences that some models wrap
# around their JSON output despite being given a structured format.
_MARKDOWN_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
)


def _extract_json(text: str) -> str:
    """Extract a JSON object from a model response.

    Some models wrap their JSON in markdown code fences, add conversational
    text before/after the JSON, or return only a fragment.  This function
    strips fences, locates the outermost ``{ … }`` brace pair, and returns
    the extracted JSON string.
    """
    stripped = text.strip()

    # 1. Strip markdown code fences first
    fence_match = _MARKDOWN_FENCE_RE.search(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()

    # 2. If the result starts with '{', assume it's already clean JSON
    if stripped.startswith("{"):
        return stripped

    # 3. Search for the first '{' and last '}' — extract the JSON blob
    start = stripped.find("{")
    if start == -1:
        return stripped  # Give up, return as-is

    # Walk forward from 'start' to find the matching closing '}'
    depth = 0
    for i in range(start, len(stripped)):
        if stripped[i] == "{":
            depth += 1
        elif stripped[i] == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : i + 1]

    # Unmatched braces — return from start to end
    return stripped[start:]


class OllamaProvider(LLMProvider):
    """Ollama LLM provider using the native HTTP API via ``httpx``."""

    def __init__(
        self,
        base_url: str = "http://ollama:11434",
        model: str = "llama3.2",
        token: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=300.0,  # LLM inference on large prompts can be slow
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
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }

        if system:
            payload["system"] = system

        if schema is not None:
            payload["format"] = schema.model_json_schema()

        try:
            resp = await self._client.post(_GENERATE_ENDPOINT, json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise AIConnectionError("ollama", self._base_url) from exc
        except httpx.TimeoutException as exc:
            raise AILLMError("ollama", f"Request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise AILLMError(
                "ollama",
                f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIConnectionError("ollama", self._base_url) from exc

        data = resp.json()
        text: str = data.get("response", "")

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
                    "ollama",
                    f"Failed to parse structured output: {exc}",
                ) from exc

        return text

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()