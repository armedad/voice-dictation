"""Shared pytest fixtures for voice-dictation-mvp."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parent.parent


def _clear_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app.main" or name.startswith("app."):
            del sys.modules[name]


@pytest.fixture
def example_voice_config() -> dict:
    raw = (ROOT / "config" / "example-model-settings.json").read_text(encoding="utf-8")
    return json.loads(raw)


@pytest.fixture
def voice_config(example_voice_config: dict):
    from core.models import VoiceDictationConfig

    return VoiceDictationConfig.model_validate(example_voice_config)


@pytest.fixture
def sample_wav() -> bytes:
    return b"RIFF....WAVEfmt "


@pytest.fixture(autouse=True)
def _voice_dictation_config_env(tmp_path, monkeypatch, example_voice_config: dict):
    """Point load_config() at a temp example config for orchestrator/API tests."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(example_voice_config), encoding="utf-8")
    monkeypatch.setenv("VOICE_DICTATION_CONFIG", str(config_file))


@pytest.fixture
def twim_api_env(tmp_path, monkeypatch):
    """Isolated twim users/logs; import app only after this runs."""
    users = tmp_path / "users"
    logs = tmp_path / "logs"
    users.mkdir()
    logs.mkdir()
    shipped_default = ROOT / "twim" / "users" / "_default"
    if shipped_default.is_dir():
        shutil.copytree(shipped_default, users / "_default")
    monkeypatch.setenv("TWIM_USERS_DIR", str(users))
    monkeypatch.setenv("TWIM_LOGS_DIR", str(logs))
    monkeypatch.setenv("TWIM_QUIET_STARTUP", "1")
    _clear_app_modules()
    yield {"users": users, "logs": logs}
    _clear_app_modules()


@pytest.fixture
async def async_client(twim_api_env):  # noqa: ARG001
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
