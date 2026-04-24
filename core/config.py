from __future__ import annotations

import json
import os
from pathlib import Path

from .models import VoiceDictationConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = REPO_ROOT / "config" / "example-model-settings.json"


def default_config_path() -> Path:
    override = os.environ.get("VOICE_DICTATION_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".voice-dictation" / "config.json"


def load_config() -> VoiceDictationConfig:
    path = default_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if EXAMPLE_CONFIG.exists():
            path.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise FileNotFoundError(
                f"No config at {path} and example missing at {EXAMPLE_CONFIG}"
            )
    data = json.loads(path.read_text(encoding="utf-8"))
    return VoiceDictationConfig.model_validate(data)


def api_key_for_transcription() -> str:
    return (
        os.environ.get("VOICE_DICTATION_TRANSCRIPTION_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()


def api_key_for_cleanup() -> str:
    return (
        os.environ.get("VOICE_DICTATION_CLEANUP_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
