"""OPENAI_COMPATIBLE provider tests — mocked httpx + env-gated real call.

Mock tests never touch the network: requests are replayed through
``httpx.MockTransport``.  The genuine manifold-gateway call is
**environment-gated** (``PILGRIM_RUN_LLM=1`` plus ``LLM_API_KEY`` /
``LLM_MODEL``) and skips by default everywhere, including CI.
"""

import json
import os
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AIConnectionError, AILLMError
from app.integrations.llm_base import create_llm_provider
from app.integrations.openai_client import OpenAICompatibleProvider


class Spec(BaseModel):
    """Toy structured-output schema."""

    title: str
    count: int


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str = "sk-test",
) -> OpenAICompatibleProvider:
    """Provider wired to an in-process MockTransport."""
    return OpenAICompatibleProvider(
        base_url="https://llm.example/v1",
        model="test-model",
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


class Recorder:
    """Handler capturing the outgoing request for assertions."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.request: httpx.Request | None = None
        self.payload: dict[str, Any] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        self.payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": self.content}}
                ]
            },
            request=request,
        )


class TestGenerate:
    async def test_plain_text_generation(self) -> None:
        rec = Recorder("hello world")
        out = await make_provider(rec).generate(prompt="say hi")
        assert out == "hello world"
        assert rec.payload is not None
        assert rec.payload["model"] == "test-model"
        assert rec.payload["messages"][0] == {
            "role": "user",
            "content": "say hi",
        }
        assert rec.payload["stream"] is False

    async def test_bearer_header_sent_when_key_present(self) -> None:
        rec = Recorder("ok")
        await make_provider(rec, api_key="sk-live").generate(prompt="x")
        assert rec.request is not None
        headers = rec.request.headers
        assert headers["authorization"] == "Bearer sk-live"

    async def test_no_auth_header_for_empty_key(self) -> None:
        rec = Recorder("ok")
        await make_provider(rec, api_key="").generate(prompt="x")
        assert rec.request is not None
        assert "authorization" not in rec.request.headers

    async def test_system_message_precedes_user(self) -> None:
        rec = Recorder("ok")
        await make_provider(rec).generate(prompt="u", system="s")
        assert rec.payload is not None
        roles = [m["role"] for m in rec.payload["messages"]]
        assert roles == ["system", "user"]

    async def test_model_override_per_call(self) -> None:
        rec = Recorder("ok")
        await make_provider(rec).generate(prompt="x", model="other")
        assert rec.payload is not None
        assert rec.payload["model"] == "other"

    async def test_structured_output_validates_schema(self) -> None:
        rec = Recorder('{"title": "Report", "count": 3}')
        result = await make_provider(rec).generate(prompt="x", schema=Spec)
        assert isinstance(result, Spec)
        assert result.title == "Report"
        assert result.count == 3

    async def test_structured_output_requests_json_mode(self) -> None:
        rec = Recorder('{"title": "R", "count": 1}')
        await make_provider(rec).generate(prompt="x", schema=Spec)
        assert rec.payload is not None
        assert rec.payload["response_format"] == {"type": "json_object"}

    async def test_markdown_fenced_json_is_extracted(self) -> None:
        rec = Recorder('Sure! ```json\n{"title": "R", "count": 2}\n```')
        result = await make_provider(rec).generate(prompt="x", schema=Spec)
        assert isinstance(result, Spec)
        assert result.count == 2


class TestErrors:
    async def test_http_error_maps_to_aillmerror(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized", request=request)

        with pytest.raises(AILLMError) as excinfo:
            await make_provider(handler).generate(prompt="x")
        assert "HTTP 401" in str(excinfo.value)

    async def test_connect_error_maps_to_aiconnectionerror(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope", request=request)

        with pytest.raises(AIConnectionError):
            await make_provider(handler).generate(prompt="x")

    async def test_timeout_maps_to_aillmerror(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(AILLMError):
            await make_provider(handler).generate(prompt="x")

    async def test_unexpected_response_shape(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"weird": True}, request=request)

        with pytest.raises(AILLMError):
            await make_provider(handler).generate(prompt="x")

    async def test_unparseable_structured_output(self) -> None:
        rec = Recorder("I am not json at all")
        with pytest.raises(AILLMError):
            await make_provider(rec).generate(prompt="x", schema=Spec)


class TestFactoryWiring:
    def test_settings_selects_openai_compatible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PILGRIM_AI_ENABLED", "true")
        monkeypatch.setenv("PILGRIM_LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
        monkeypatch.setenv("LLM_API_KEY", "sk-abc")
        monkeypatch.setenv("LLM_MODEL", "gpt-x")
        get_settings.cache_clear()
        try:
            provider_obj = create_llm_provider()
            assert isinstance(provider_obj, OpenAICompatibleProvider)
        finally:
            get_settings.cache_clear()

    def test_default_settings_still_use_ollama(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PILGRIM_AI_ENABLED", "true")
        monkeypatch.delenv("PILGRIM_LLM_PROVIDER", raising=False)
        get_settings.cache_clear()
        try:
            from app.integrations.ollama_client import OllamaProvider

            assert isinstance(create_llm_provider(), OllamaProvider)
        finally:
            get_settings.cache_clear()


# ── Real gateway smoke (default-skipped) ─────────────────────────


@pytest.mark.skipif(
    os.environ.get("PILGRIM_RUN_LLM") != "1",
    reason="real LLM call; set PILGRIM_RUN_LLM=1 (and LLM_API_KEY/LLM_MODEL) "
    "to run",
)
class TestRealManifold:
    async def test_real_gateway_plain_and_structured(self) -> None:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_model:
            pytest.skip(
                "LLM_API_KEY / LLM_MODEL not configured; nothing to call"
            )
        provider_obj = OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
        )
        try:
            text = await provider_obj.generate(
                prompt="Reply with the word: ping"
            )
            assert isinstance(text, str)
            assert "ping" in text.lower()

            structured = await provider_obj.generate(
                prompt=(
                    "Produce a JSON object with keys title (string) and "
                    "count (integer), e.g. "
                    '{"title": "test", "count": 1}.'
                ),
                schema=Spec,
            )
            assert isinstance(structured, Spec)
        finally:
            await provider_obj.close()
