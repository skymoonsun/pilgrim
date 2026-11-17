"""Field-mapping engine: non-string literals must not crash resolution.

Regression for the 2026-11-18 live-E2E callback FAILURE (kanban
t_c503edb9): a template ``field_mapping`` entry with an int literal
(``"app_id": 620``) made ``_resolve_path`` call ``path.startswith("$.")``
on an ``int`` — the ``AttributeError`` bubbled out of
``CallbackService.execute_callback`` and the attempt was logged as
FAILURE, even though the value is a legal literal, not a path.

Contract after the fix:

- non-string ``path`` values (int/float/bool/None) are returned as-is;
- string behavior is unchanged (non-``$.`` literal passthrough,
  ``$.``-path resolution, missing segment → ``None``);
- both consumers of the shared engine are covered: webhook
  ``CallbackService._build_payload`` and email
  ``EmailNotificationService._build_email_body``.

No database is touched — the mapping engine methods are static and read
plain model attributes.
"""

import uuid
from typing import Any

import pytest

from app.models.callback_config import CallbackConfig
from app.models.email_notification_config import EmailNotificationConfig
from app.services.callback_service import CallbackService, _resolve_path
from app.services.email_notification_service import EmailNotificationService

# ── Helpers ──────────────────────────────────────────────────────────


def _context() -> dict[str, Any]:
    """Standard resolution context mirroring _build_payload's shape."""
    return {
        "data": {"title": "Portal 2", "price": 51.77},
        "url": "https://store.example/portal-2",
        "metadata": {"http_status": 200, "timestamp": "2026-11-18T00:00:00Z"},
    }


def _results() -> list[dict[str, Any]]:
    return [
        {
            "data": {"title": "Portal 2", "price": 51.77},
            "url": "https://store.example/portal-2",
            "http_status": 200,
        }
    ]


# ── _resolve_path: literal tolerance + unchanged string behavior ────


class TestResolvePathLiterals:
    @pytest.mark.parametrize("literal", [620, 62.5, True, None])
    def test_non_string_literals_returned_as_is(
        self, literal: Any
    ) -> None:
        # Pre-fix this raised AttributeError: 'int' object has no
        # attribute 'startswith' (620), 'float' (62.5), 'bool' (True),
        # 'NoneType' (None).
        assert _resolve_path(_context(), literal) is literal

    def test_str_literal_passes_through_unchanged(self) -> None:
        assert _resolve_path(_context(), "620") == "620"
        assert _resolve_path(_context(), "steam") == "steam"

    def test_dollar_paths_still_resolve(self) -> None:
        ctx = _context()
        assert _resolve_path(ctx, "$.data.title") == "Portal 2"
        assert _resolve_path(ctx, "$.data.price") == 51.77
        assert _resolve_path(ctx, "$.url") == "https://store.example/portal-2"
        assert _resolve_path(ctx, "$.metadata.http_status") == 200

    def test_missing_segment_returns_none(self) -> None:
        ctx = _context()
        assert _resolve_path(ctx, "$.data.missing") is None
        assert _resolve_path(ctx, "$.data.title.nested") is None  # str non-dict
        assert _resolve_path(ctx, "$.nope") is None


# ── _build_payload: the exact live-E2E FAILURE shape ────────────────


def _config(
    field_mapping: dict[str, Any], *, batched: bool = False
) -> CallbackConfig:
    return CallbackConfig(
        url="https://cb.example/hook",
        field_mapping=field_mapping,
        batch_results=batched,
        include_metadata=False,
    )


class TestBuildPayloadIntLiteral:
    def test_int_literal_field_mapping_builds_payload(self) -> None:
        # The exact shape from the live E2E: app_id as an int literal.
        config = _config(
            {
                "field_mapping": {
                    "app_id": 620,
                    "title": "$.data.title",
                    "source": "$.url",
                },
                "static_fields": {"source_system": "pilgrim"},
            }
        )

        payload = CallbackService._build_payload(config, _results(), None)

        assert payload["app_id"] == 620
        assert isinstance(payload["app_id"], int)  # not the "620" workaround
        assert payload["title"] == "Portal 2"
        assert payload["source"] == "https://store.example/portal-2"
        assert payload["source_system"] == "pilgrim"

    def test_int_literal_in_batch_mode_with_wrap_key(self) -> None:
        config = _config(
            {
                "field_mapping": {"app_id": 620, "title": "$.data.title"},
                "wrap_key": "results",
            },
            batched=True,
        )

        payload = CallbackService._build_payload(config, _results(), None)

        assert len(payload["results"]) == 1
        assert payload["results"][0] == {"app_id": 620, "title": "Portal 2"}


# ── Email consumer shares the engine — same literal tolerance ───────


class TestEmailBodyIntLiteral:
    def test_int_literal_field_mapping_renders_in_email_body(self) -> None:
        config = EmailNotificationConfig(
            schedule_id=uuid.uuid4(),
            recipient_emails=["qa@example.com"],
            field_mapping={
                "field_mapping": {
                    "app_id": 620,
                    "title": "$.data.title",
                }
            },
            include_metadata=False,
        )

        body = EmailNotificationService._build_email_body(
            config, _results(), {}, "success"
        )

        assert "<td>620</td>" in body
        assert "Portal 2" in body
