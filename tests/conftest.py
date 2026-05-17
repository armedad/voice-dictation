"""Shared pytest fixtures for voice-dictation-mvp."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def example_voice_config() -> dict:
    import json

    raw = (ROOT / "config" / "example-model-settings.json").read_text(encoding="utf-8")
    return json.loads(raw)
