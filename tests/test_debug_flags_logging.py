"""Tests for core.debug_flags_logging — flag normalization and per-user lookup."""

from __future__ import annotations

import json

import pytest

import core.debug_flags_logging as dbg


class TestIsFlagEnabledForUser:
    def test_unknown_user_uses_defaults(self) -> None:
        assert dbg.is_flag_enabled_for_user("", "AUTH") is True
        assert dbg.is_flag_enabled_for_user("", "API") is False

    def test_reads_user_settings(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        users = tmp_path / "users"
        users.mkdir()
        settings = users / "alice" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps({"debug_flags": {"API": True, "DICTATION": True}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(dbg, "_USERS_DIR", users)

        assert dbg.is_flag_enabled_for_user("alice", "api") is True
        assert dbg.is_flag_enabled_for_user("alice", "DICTATION") is True
        assert dbg.is_flag_enabled_for_user("alice", "CHAT") is True

    def test_missing_file_falls_back_to_defaults(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        users = tmp_path / "users"
        users.mkdir()
        monkeypatch.setattr(dbg, "_USERS_DIR", users)
        assert dbg.is_flag_enabled_for_user("nobody", "SETTINGS") is False


class TestLogDebug:
    def test_skips_when_flag_disabled(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        users = tmp_path / "users"
        logs = tmp_path / "logs"
        users.mkdir()
        logs.mkdir()
        (users / "bob" / "settings.json").parent.mkdir(parents=True)
        (users / "bob" / "settings.json").write_text(
            json.dumps({"debug_flags": {"API": False}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(dbg, "_USERS_DIR", users)
        monkeypatch.setattr(dbg, "_LOGS_DIR", logs)

        dbg.log_debug(username="bob", flag="API", level="info", message="should not appear")
        log_files = list(logs.glob("twim_*.log"))
        assert log_files == []

    def test_writes_when_flag_enabled(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        users = tmp_path / "users"
        logs = tmp_path / "logs"
        users.mkdir()
        logs.mkdir()
        (users / "bob" / "settings.json").parent.mkdir(parents=True)
        (users / "bob" / "settings.json").write_text(
            json.dumps({"debug_flags": {"API": True}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(dbg, "_USERS_DIR", users)
        monkeypatch.setattr(dbg, "_LOGS_DIR", logs)

        dbg.log_debug(username="bob", flag="API", level="info", message="hello", data={"x": 1})
        log_files = list(logs.glob("twim_*.log"))
        assert len(log_files) == 1
        text = log_files[0].read_text(encoding="utf-8")
        assert "hello" in text
        assert "DEBUG_INFO" in text
