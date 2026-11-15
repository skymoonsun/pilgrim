"""JWT secret hygiene tests — placeholder guard + length enforcement.

Covers the post-#15 review nits: the built-in placeholder must be long
enough for HS256 (no pyjwt ``InsecureKeyLengthWarning``), explicitly set
secrets shorter than 32 bytes are rejected outright by ``Settings``, and
startup (``guard_jwt_secret``) warns loudly on the placeholder in
read-open mode / refuses to boot strict mode on it.  Also locks the
create-user CLI warning for ``--password`` argv exposure.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import warnings
from pathlib import Path

import jwt as pyjwt
import pytest
from jwt.warnings import InsecureKeyLengthWarning
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_JWT_SECRET,
    MIN_JWT_SECRET_BYTES,
    Settings,
    get_settings,
)
from app.core.security import guard_jwt_secret


def test_default_secret_meets_hs256_length() -> None:
    assert len(DEFAULT_JWT_SECRET.encode("utf-8")) >= MIN_JWT_SECRET_BYTES


def test_default_secret_does_not_trigger_pyjwt_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pyjwt.encode({"sub": "user-1"}, DEFAULT_JWT_SECRET, algorithm="HS256")
    insecure = [
        w for w in caught if issubclass(w.category, InsecureKeyLengthWarning)
    ]
    assert insecure == []


def _build_settings(monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    """Build ``Settings`` with extra env overrides (DATABASE_URL/REDIS_URL
    are already provided by the conftest module-level defaults)."""
    for key, value in extra.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


class TestSecretLengthEnforcement:
    def test_short_explicit_secret_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(ValidationError) as excinfo:
            _build_settings(monkeypatch, PILGRIM_JWT_SECRET="too-short")
        assert "at least 32 bytes" in str(excinfo.value)

    def test_multibyte_secret_measured_in_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 10 snowmen = 10 characters but 30 utf-8 bytes → rejected.
        snowmen = "☃" * 10
        assert len(snowmen) < MIN_JWT_SECRET_BYTES
        with pytest.raises(ValidationError):
            _build_settings(monkeypatch, PILGRIM_JWT_SECRET=snowmen)

    def test_exact_32_byte_secret_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "a" * MIN_JWT_SECRET_BYTES
        settings = _build_settings(monkeypatch, PILGRIM_JWT_SECRET=secret)
        assert settings.jwt_secret == secret

    def test_unset_secret_falls_back_to_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _build_settings(monkeypatch).jwt_secret == DEFAULT_JWT_SECRET


class TestGuardJwtSecret:
    def test_read_open_placeholder_warns_loudly(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        guard_jwt_secret(_build_settings(monkeypatch))  # must not raise
        assert any(
            "PILGRIM_JWT_SECRET" in record.message
            and record.levelno >= 30  # WARNING or louder
            for record in caplog.records
        )

    def test_read_open_custom_secret_is_silent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings = _build_settings(
            monkeypatch, PILGRIM_JWT_SECRET="a" * MIN_JWT_SECRET_BYTES
        )
        guard_jwt_secret(settings)
        assert not any(record.levelno >= 30 for record in caplog.records)

    def test_strict_placeholder_refuses_to_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _build_settings(monkeypatch, PILGRIM_AUTH_MODE="strict")
        with pytest.raises(RuntimeError) as excinfo:
            guard_jwt_secret(settings)
        assert "PILGRIM_JWT_SECRET" in str(excinfo.value)

    def test_strict_custom_secret_boots(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _build_settings(
            monkeypatch,
            PILGRIM_AUTH_MODE="strict",
            PILGRIM_JWT_SECRET="a" * MIN_JWT_SECRET_BYTES,
        )
        guard_jwt_secret(settings)  # no raise


_CLI_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "cli" / "create_user.py"
)


def _load_cli_module(
    monkeypatch: pytest.MonkeyPatch, calls: dict[str, str]
) -> types.ModuleType:
    """Import the CLI fresh with ``_create_user`` stubbed (no DB)."""
    spec = importlib.util.spec_from_file_location(
        "create_user_under_test", _CLI_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def fake_create_user(username: str, password: str | None) -> int:
        calls["username"] = username
        calls["password"] = password or ""
        return 0

    monkeypatch.setattr(module, "_create_user", fake_create_user)
    monkeypatch.setitem(sys.modules, "create_user_under_test", module)
    return module


class TestCreateUserArgvPasswordWarning:
    """create_user main() warns when a plaintext password rides argv."""

    def test_argv_password_prints_ps_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: dict[str, str] = {}
        monkeypatch.setattr(
            sys, "argv", ["create_user", "ops", "--password", "hunter2"]
        )
        module = _load_cli_module(monkeypatch, calls)
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert excinfo.value.code == 0
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert "`ps`" in err
        assert calls["password"] == "hunter2"

    def test_generated_password_path_stays_quiet(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: dict[str, str] = {}
        monkeypatch.setattr(sys, "argv", ["create_user", "ops"])
        module = _load_cli_module(monkeypatch, calls)
        with pytest.raises(SystemExit):
            module.main()
        assert "WARNING" not in capsys.readouterr().err
        # No explicit password reached the stub → the real CLI generates one.
        assert calls["password"] == ""
