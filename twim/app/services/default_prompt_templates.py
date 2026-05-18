"""Update shipped new-user dictation cleanup prompt templates on disk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.users import USERS_DIR

VOICE_DICTATION_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SETTINGS_PATH = USERS_DIR / "_default" / "settings.json"
INSTALL_SEED_PATH = VOICE_DICTATION_ROOT / "config" / "default-twim-settings.json"

SYSTEM_KEY = "dictation_cleanup_system_prompt_template"
USER_KEY = "dictation_cleanup_user_prompt_template"


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object at top level")
    return data


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _patch_prompt_keys(
    path: Path, system_template: str, user_template: str
) -> None:
    data = _load_json_object(path)
    data[SYSTEM_KEY] = system_template
    data[USER_KEY] = user_template
    _write_json_object(path, data)


def update_shipped_default_prompt_templates(
    system_template: str,
    user_template: str,
) -> list[str]:
    """
    Write system and user cleanup templates into new-user default files.

    Updates ``twim/users/_default/settings.json`` and
    ``config/default-twim-settings.json`` (install seed). Other keys are preserved.

    Returns repo-relative path strings for each file updated.
    """
    system = (system_template or "").strip()
    user = (user_template or "").strip()
    if not system:
        raise ValueError("dictation_cleanup_system_prompt_template must not be empty")
    if not user:
        raise ValueError("dictation_cleanup_user_prompt_template must not be empty")

    paths = (DEFAULT_SETTINGS_PATH, INSTALL_SEED_PATH)
    for path in paths:
        _patch_prompt_keys(path, system, user)

    updated: list[str] = []
    try:
        updated.append(str(DEFAULT_SETTINGS_PATH.relative_to(VOICE_DICTATION_ROOT)))
    except ValueError:
        updated.append(str(DEFAULT_SETTINGS_PATH))
    try:
        updated.append(str(INSTALL_SEED_PATH.relative_to(VOICE_DICTATION_ROOT)))
    except ValueError:
        updated.append(str(INSTALL_SEED_PATH))
    return updated
