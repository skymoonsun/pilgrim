"""Callback delivery: ``trust_scores`` transform + env-secret headers.

- ``field_mapping = {"transform": "trust_scores"}`` folds per-job crawl
  results into the single trust document (per-domain ``scores``, a
  ``failed`` list, ``crawled_at``); ``transform`` and the per-row field
  mapping are mutually exclusive.
- ``batch_results`` False → the payload IS the document; True → the
  document rides under the ``results`` key.
- Header values shaped like ``{{ENV_NAME}}`` resolve from the
  environment at dispatch; unset/empty env drops the header (the
  warning names the env var, never the resolved secret).
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callback_config import CallbackConfig
from app.models.enums import CallbackMethod
from app.services.callback_service import (
    CallbackService,
    _build_trust_document,
    resolve_env_placeholder,
)

TRUST_REVIEW_URL = "https://www.trustpilot.com/review/kinguin.net"
GOG_REVIEW_URL = "https://www.trustpilot.com/review/gog.com"

KINGUIN_EXTRACTION: dict[str, Any] = {
    "trust_score": 4.6,
    "review_count": 125805,
    "trust_score_nd": None,
    "review_count_nd": None,
    "trust_score_css": None,
    "review_count_css": None,
    "stars": 4.5,
    "display_name": "Kinguin.net",
    "identifying_name": "kinguin.net",
}

UNUSABLE_EXTRACTION: dict[str, Any] = {
    name: None
    for name in (
        "trust_score", "review_count", "trust_score_nd", "review_count_nd",
        "trust_score_css", "review_count_css", "stars", "display_name",
        "identifying_name",
    )
}


def _config(**overrides: Any) -> CallbackConfig:
    """Unpersisted CallbackConfig — ``_build_payload`` reads attributes
    only (model defaults apply on flush, so everything it touches is
    passed explicitly)."""
    values: dict[str, Any] = {
        "id": uuid4(),
        "schedule_id": uuid4(),
        "url": "https://hooks.example/trust",
        "method": CallbackMethod.POST,
        "headers": {"X-Webhook-Secret": "{{PILGRIM_TEST_WEBHOOK_SECRET}}"},
        "field_mapping": {"transform": "trust_scores"},
        "include_metadata": False,
        "batch_results": False,
        "retry_count": 0,
        "retry_delay_seconds": 60,
        "is_active": True,
    }
    values.update(overrides)
    return CallbackConfig(**values)


class _FakeResponse:
    status_code = 204
    text = "ok"


_UNSET: dict[str, str] | None = object()  # type: ignore[assignment]


async def _sent_requests(
    db_session: AsyncSession,
    headers: Any = _UNSET,
) -> list[dict[str, Any]]:
    """Run one real ``_send_request`` with httpx stubbed; return the
    captured request kwargs (one entry — 204 → no retry round).
    ``headers`` left unpassed keeps the config's placeholder header."""
    captured: list[dict[str, Any]] = []

    def _client_factory(**_kwargs: Any) -> Any:
        class _Client:
            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *exc_info: Any) -> None:
                return None

            async def request(self, **kwargs: Any) -> Any:
                captured.append(kwargs)
                return _FakeResponse()

        return _Client()  # instance — AsyncClient(timeout=...) → CM object

    with patch(
        "app.services.callback_service.httpx.AsyncClient", _client_factory
    ):
        service = CallbackService(db_session)
        overrides = {} if headers is _UNSET else {"headers": headers}
        log = await service._send_request(
            _config(**overrides),
            {"ok": True},
            None,
            1,
        )
        assert log.success is True
    return captured


class TestTrustScoresTransform:
    def test_rows_build_the_document(self) -> None:
        results = [{
            "url": TRUST_REVIEW_URL,
            "data": dict(KINGUIN_EXTRACTION),
            "http_status": 200,
        }]
        payload = CallbackService._build_payload(_config(), results, None)

        assert payload["source"] == "trustpilot"
        assert payload["scale"] == 5
        assert payload["scores"]["kinguin.net"] == {
            "score": 4.6,
            "reviews": 125805,
            "stars": 4.5,
            "name": "Kinguin.net",
            "url": TRUST_REVIEW_URL,
        }
        assert payload["failed"] == []
        crawled_at = datetime.fromisoformat(payload["crawled_at"])
        assert crawled_at.tzinfo is not None
        assert abs((datetime.now(UTC) - crawled_at).total_seconds()) < 10

    def test_document_rides_on_batch_results_with_metadata(self) -> None:
        results = [{"url": TRUST_REVIEW_URL, "data": dict(KINGUIN_EXTRACTION)}]
        payload = CallbackService._build_payload(
            _config(batch_results=True), results, {"schedule_id": "s1"},
        )
        assert set(payload) == {"results"}
        assert payload["results"]["scores"]["kinguin.net"]["score"] == 4.6

    def test_domain_is_derived_and_normalized_from_the_row_url(self) -> None:
        doc = _build_trust_document([
            {"url": "https://www.trustpilot.com/review/www.gog.com",
             "data": {"trust_score": 4.5}},
        ])
        assert set(doc["scores"]) == {"gog.com"}

    def test_failed_list_captured_and_first_usable_wins(self) -> None:
        results = [
            # kinguin.net: first row unusable, second usable → the
            # usable one wins and the domain is NOT failed.
            {"url": TRUST_REVIEW_URL, "data": dict(UNUSABLE_EXTRACTION)},
            {"url": TRUST_REVIEW_URL, "data": dict(KINGUIN_EXTRACTION)},
            # gog.com: never usable → failed.
            {"url": GOG_REVIEW_URL, "data": dict(UNUSABLE_EXTRACTION)},
        ]
        doc = _build_trust_document(results)

        assert doc["scores"]["kinguin.net"]["score"] == 4.6
        assert doc["failed"] == ["gog.com"]

    def test_transform_and_per_row_mapping_are_exclusive(self) -> None:
        mapping = {
            "transform": "trust_scores",
            "field_mapping": {"title": "$.data.x"},
            "static_fields": {"injected": "nope"},
            "wrap_key": "payload",
        }
        payload = CallbackService._build_payload(
            _config(field_mapping=mapping),
            [{"url": TRUST_REVIEW_URL, "data": dict(KINGUIN_EXTRACTION)}],
            {"schedule_id": "abc"},
        )
        # Transform wins wholesale: no per-row key, no static field, no
        # wrap_key, no _metadata — the raw document exactly.
        assert set(payload) == {"source", "scale", "scores", "failed", "crawled_at"}

    def test_rows_without_review_url_are_skipped(self) -> None:
        doc = _build_trust_document([
            {"url": "https://example.com/product/1", "data": {"trust_score": 5}},
            {"url": "", "data": {"trust_score": 4}},
        ])
        assert doc["scores"] == {}
        assert doc["failed"] == []

    def test_empty_results_still_deliver_the_document_skeleton(self) -> None:
        doc = CallbackService._build_payload(_config(), [], None)
        assert doc["source"] == "trustpilot"
        assert doc["scores"] == {}
        assert doc["failed"] == []
        assert "crawled_at" in doc

    def test_classic_per_row_mapping_still_works(self) -> None:
        mapping = {"field_mapping": {"title": "$.data.trust_score"}}
        payload = CallbackService._build_payload(
            _config(
                field_mapping=mapping, batch_results=False,
                headers=None, include_metadata=False,
            ),
            [{"url": "https://shop.example/p/1", "data": {"trust_score": 4.1}}],
            None,
        )
        assert payload == {"title": 4.1}  # untouched legacy path


class TestResolveEnvPlaceholder:
    def test_resolves_from_environment(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PILGRIM_TEST_TOKEN", "t0ken")
        assert resolve_env_placeholder("{{PILGRIM_TEST_TOKEN}}") == "t0ken"

    def test_unset_env_returns_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PILGRIM_TEST_TOKEN", raising=False)
        assert resolve_env_placeholder("{{PILGRIM_TEST_TOKEN}}") is None

    def test_empty_env_returns_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PILGRIM_TEST_TOKEN", "")
        assert resolve_env_placeholder("{{PILGRIM_TEST_TOKEN}}") is None

    def test_underscore_and_digits_in_the_name(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        underscore_digits = "leading-underscore is still a name"
        monkeypatch.setenv("_OK_1", underscore_digits)
        assert resolve_env_placeholder("{{_OK_1}}") == underscore_digits

    @pytest.mark.parametrize(
        "value",
        ["Bearer raw", "{X}", "{{lower_case}}", "{{X", "{{A}}{{B}}", "  {{A}}  "],
    )
    def test_everything_else_passes_through(self, value: str) -> None:
        assert resolve_env_placeholder(value) == value

    def test_non_string_values_pass_through(self) -> None:
        assert resolve_env_placeholder(42) == 42
        assert resolve_env_placeholder(None) is None


class TestEnvHeaderDispatch:
    async def test_placeholder_resolved_when_env_set(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PILGRIM_TEST_WEBHOOK_SECRET", "whsec_abc123")
        sent = await _sent_requests(db_session)
        assert sent
        assert sent[0]["headers"]["X-Webhook-Secret"] == "whsec_abc123"

    async def test_placeholder_dropped_when_env_unset(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.delenv("PILGRIM_TEST_WEBHOOK_SECRET", raising=False)
        with caplog.at_level("WARNING"):
            sent = await _sent_requests(db_session)
        assert sent
        assert "X-Webhook-Secret" not in sent[0]["headers"]
        assert sent[0]["headers"]["Content-Type"] == "application/json"
        # The warning names the env var, never any secret value.
        assert "PILGRIM_TEST_WEBHOOK_SECRET" in caplog.text

    async def test_placeholder_dropped_when_env_empty(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PILGRIM_TEST_WEBHOOK_SECRET", "")
        sent = await _sent_requests(db_session)
        assert sent
        assert "X-Webhook-Secret" not in sent[0]["headers"]

    async def test_resolved_secret_never_reaches_the_logs(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("PILGRIM_TEST_WEBHOOK_SECRET", "whsec_live_9f2f0")
        with caplog.at_level("WARNING"):
            sent = await _sent_requests(db_session)
        assert sent
        assert sent[0]["headers"]["X-Webhook-Secret"] == "whsec_live_9f2f0"
        assert "whsec_live_9f2f0" not in caplog.text

    async def test_plain_header_values_pass_through(
        self, db_session: AsyncSession,
    ) -> None:
        sent = await _sent_requests(
            db_session, headers={"X-Trace": "static-value"}
        )
        assert sent
        assert sent[0]["headers"]["X-Trace"] == "static-value"
