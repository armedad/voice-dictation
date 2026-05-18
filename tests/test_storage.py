"""Tests for twim.app.services.storage — small pure helpers."""

from __future__ import annotations

import json

import pytest

from app.services.storage import (
    DEBUG_FLAG_DEFAULTS,
    Settings,
    UserDataStore,
    get_default_settings,
    normalize_debug_flags,
    normalize_url,
    require_default_model,
)


class TestNormalizeDebugFlags:
    def test_returns_defaults_when_none(self) -> None:
        assert normalize_debug_flags(None) == dict(DEBUG_FLAG_DEFAULTS)

    def test_unknown_keys_ignored(self) -> None:
        out = normalize_debug_flags({"AUTH": False, "NOPE": True})
        assert out["AUTH"] is False
        assert "NOPE" not in out

    def test_coerces_to_bool(self) -> None:
        out = normalize_debug_flags({"DICTATION": 1})
        assert out["DICTATION"] is True


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("localhost:1234", "http://localhost:1234"),
            ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
            ("https://api.example.com", "https://api.example.com"),
            ("", ""),
        ],
    )
    def test_adds_http_when_missing(self, raw: str, expected: str) -> None:
        assert normalize_url(raw) == expected


class TestRequireDefaultModel:
    def test_raises_when_missing(self) -> None:
        settings = Settings(default_model=None, default_provider="ollama")
        with pytest.raises(ValueError, match="default_model is not set"):
            require_default_model(settings, source="test settings")

    def test_raises_when_blank(self) -> None:
        settings = Settings(default_model="  ", default_provider="ollama")
        with pytest.raises(ValueError, match="default_model is not set"):
            require_default_model(settings)

    def test_passes_when_set(self) -> None:
        settings = Settings(
            default_model="llama3.2:3b",
            default_provider="ollama",
        )
        require_default_model(settings)

    def test_get_default_settings_loads_shipped_model(self) -> None:
        settings = get_default_settings()
        assert settings.default_model == "qwen2.5:7b-instruct"

    def test_get_default_settings_raises_without_shipped_file(
        self, tmp_path, monkeypatch
    ) -> None:
        users_dir = tmp_path / "users"
        users_dir.mkdir()
        monkeypatch.delenv("TWIM_USERS_DIR", raising=False)
        monkeypatch.setattr("app.services.users.USERS_DIR", users_dir)
        with pytest.raises(ValueError, match="Missing or invalid shipped defaults"):
            get_default_settings()

    def test_new_user_store_get_settings(self, tmp_path, monkeypatch) -> None:
        users = tmp_path / "users"
        default_dir = users / "_default"
        default_dir.mkdir(parents=True)
        (default_dir / "settings.json").write_text(
            json.dumps(
                {
                    "default_model": "qwen2.5:7b-instruct",
                    "default_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.delenv("TWIM_USERS_DIR", raising=False)
        monkeypatch.setattr("app.services.users.USERS_DIR", users)
        store = UserDataStore(users / "newuser", "newuser")
        settings = store.get_settings()
        assert settings.default_model == "qwen2.5:7b-instruct"
