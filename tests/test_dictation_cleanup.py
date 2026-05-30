"""Tests for twim.app.services.dictation_cleanup — endpoint resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.dictation_cleanup import (
    build_cleanup_endpoint,
    resolve_transcription_endpoint,
)
from app.services.storage import Settings
from core.models import VoiceDictationConfig


@pytest.fixture
def voice_config(example_voice_config: dict) -> VoiceDictationConfig:
    return VoiceDictationConfig.model_validate(example_voice_config)


class TestResolveTranscriptionEndpoint:
    def test_empty_setting_uses_disk_config(self, voice_config: VoiceDictationConfig) -> None:
        ep = resolve_transcription_endpoint(None, voice_config)
        assert ep.provider == "faster_whisper"
        assert ep.model_name == "base"

    def test_legacy_bare_model_id(self, voice_config: VoiceDictationConfig) -> None:
        ep = resolve_transcription_endpoint("small", voice_config)
        assert ep.provider == "faster_whisper"
        assert ep.model_name == "small"

    def test_provider_colon_model(self, voice_config: VoiceDictationConfig) -> None:
        ep = resolve_transcription_endpoint(
            "openai_compatible_audio:whisper-1", voice_config
        )
        assert ep.provider == "openai_compatible_audio"
        assert ep.model_name == "whisper-1"
        assert ep.baseURL == voice_config.transcription.baseURL


class TestBuildCleanupEndpoint:
    def test_ollama(self, tmp_path: Path) -> None:
        settings = Settings(
            default_provider="ollama",
            default_model="llama3.2",
            ollama_url="http://127.0.0.1:11434/",
        )
        ep, key = build_cleanup_endpoint(settings, tmp_path)
        assert ep.provider == "ollama_chat"
        assert ep.model_name == "llama3.2"
        assert ep.baseURL == "http://127.0.0.1:11434"
        assert key is None

    def test_local_lm_studio(self, tmp_path: Path) -> None:
        settings = Settings(
            default_provider="local",
            default_model="local-model",
            lm_studio_url="http://localhost:1234/",
        )
        ep, key = build_cleanup_endpoint(settings, tmp_path)
        assert ep.provider == "openai_compatible_chat"
        assert ep.baseURL == "http://localhost:1234/v1"
        assert key == ""

    def test_missing_model_raises(self, tmp_path: Path) -> None:
        settings = Settings(default_provider="ollama", default_model=None)
        with pytest.raises(ValueError, match="default model"):
            build_cleanup_endpoint(settings, tmp_path)

    def test_cloud_provider_with_key(self, tmp_path: Path) -> None:
        providers = {
            "providers": {
                "openai": {
                    "name": "OpenAI",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                    "api_format": "openai",
                    "enabled": True,
                    "models": [],
                    "custom": False,
                }
            }
        }
        (tmp_path / "providers.json").write_text(
            json.dumps(providers), encoding="utf-8"
        )
        settings = Settings(default_provider="openai", default_model="gpt-4o-mini")
        ep, key = build_cleanup_endpoint(settings, tmp_path)
        assert ep.provider == "openai_compatible_chat"
        assert ep.model_name == "gpt-4o-mini"
        assert key == "sk-test"
