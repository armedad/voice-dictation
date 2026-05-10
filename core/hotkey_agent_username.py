"""Resolve which twim user directory the embedded hotkey sidecar uses."""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_SEED_USER = "_default"


def resolve_hotkey_agent_username(repo_root: Path) -> str:
    """
    Order: ``VOICE_DICTATION_TWIM_USER`` / legacy ``VOICE_DICTATION_AI_FRAME_USER``,
    then ``twim/users/.hotkey_agent_target_username`` (written when saving hotkeys in the UI),
    then ``_default`` if ``twim/users/_default/settings.json`` exists (install seed).
    """
    users_dir = repo_root / "twim" / "users"
    env_u = (
        os.environ.get("VOICE_DICTATION_TWIM_USER")
        or os.environ.get("VOICE_DICTATION_AI_FRAME_USER")
        or ""
    ).strip()
    if env_u:
        return env_u
    marker = users_dir / ".hotkey_agent_target_username"
    if marker.exists():
        try:
            t = marker.read_text(encoding="utf-8").strip()
        except OSError:
            t = ""
        if t and (users_dir / t).is_dir():
            return t
    seed = users_dir / _DEFAULT_SEED_USER / "settings.json"
    if seed.is_file():
        return _DEFAULT_SEED_USER
    return ""
