"""Tests for twim.app.services.storage — small pure helpers."""

from __future__ import annotations

import pytest

from app.services.storage import (
    DEBUG_FLAG_DEFAULTS,
    normalize_debug_flags,
    normalize_url,
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
