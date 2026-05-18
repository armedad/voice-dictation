"""twim settings API tests."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from helpers import attach_session_from_register


async def _register(async_client: AsyncClient) -> None:
    r = await async_client.post(
        "/api/auth/register",
        json={
            "username": "settingsuser",
            "password": "secret",
            "display_name": "Settings User",
        },
    )
    assert r.status_code == 200
    attach_session_from_register(async_client, r)


async def test_get_settings_defaults(async_client: AsyncClient) -> None:
    await _register(async_client)
    r = await async_client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["default_provider"] == "ollama"
    assert body["default_model"] == "qwen2.5:3b-instruct"
    assert "minimal edits" in (body.get("dictation_cleanup_user_prompt_template") or "")
    assert "debug_flags" in body


async def test_patch_settings_round_trip(async_client: AsyncClient) -> None:
    await _register(async_client)
    patch = await async_client.patch(
        "/api/settings",
        json={"dictation_llm_cleanup_enabled": False},
    )
    assert patch.status_code == 200
    assert patch.json()["dictation_llm_cleanup_enabled"] is False

    got = await async_client.get("/api/settings")
    assert got.json()["dictation_llm_cleanup_enabled"] is False


@pytest.fixture
def isolated_default_prompt_paths(twim_api_env, tmp_path, monkeypatch):
    """Point shipped-default writer at tmp files (avoid touching repo config/)."""
    from app.services import default_prompt_templates as dpt

    users = twim_api_env["users"]
    default_file = users / "_default" / "settings.json"
    default_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_text(
        json.dumps(
            {
                "theme": "dark",
                "dictation_cleanup_system_prompt_template": "old-system",
                "dictation_cleanup_user_prompt_template": "old-user {raw}",
            }
        ),
        encoding="utf-8",
    )
    seed = tmp_path / "default-twim-settings.json"
    seed.write_text(
        json.dumps(
            {
                "theme": "light",
                "dictation_cleanup_system_prompt_template": "seed-system",
                "dictation_cleanup_user_prompt_template": "seed-user {raw}",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dpt, "DEFAULT_SETTINGS_PATH", default_file)
    monkeypatch.setattr(dpt, "INSTALL_SEED_PATH", seed)
    return {"default_file": default_file, "seed": seed}


async def test_set_default_prompt_templates_requires_auth(
    async_client: AsyncClient,
) -> None:
    r = await async_client.post(
        "/api/settings/default-prompt-templates",
        json={
            "dictation_cleanup_system_prompt_template": "sys",
            "dictation_cleanup_user_prompt_template": "user {raw}",
        },
    )
    assert r.status_code == 401


async def test_set_default_prompt_templates_updates_files(
    async_client: AsyncClient,
    isolated_default_prompt_paths,
) -> None:
    await _register(async_client)
    r = await async_client.post(
        "/api/settings/default-prompt-templates",
        json={
            "dictation_cleanup_system_prompt_template": "NEW-SYSTEM {{ vocabulary }}",
            "dictation_cleanup_user_prompt_template": "NEW-USER\n{raw}",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body.get("updated") or []) == 2

    default_file = isolated_default_prompt_paths["default_file"]
    seed = isolated_default_prompt_paths["seed"]
    default_data = json.loads(default_file.read_text(encoding="utf-8"))
    seed_data = json.loads(seed.read_text(encoding="utf-8"))

    assert default_data["dictation_cleanup_system_prompt_template"] == (
        "NEW-SYSTEM {{ vocabulary }}"
    )
    assert default_data["dictation_cleanup_user_prompt_template"] == "NEW-USER\n{raw}"
    assert default_data["theme"] == "dark"

    assert seed_data["dictation_cleanup_system_prompt_template"] == (
        "NEW-SYSTEM {{ vocabulary }}"
    )
    assert seed_data["dictation_cleanup_user_prompt_template"] == "NEW-USER\n{raw}"
    assert seed_data["theme"] == "light"


async def test_set_default_prompt_templates_rejects_empty(
    async_client: AsyncClient,
    isolated_default_prompt_paths,
) -> None:
    await _register(async_client)
    r = await async_client.post(
        "/api/settings/default-prompt-templates",
        json={
            "dictation_cleanup_system_prompt_template": "   ",
            "dictation_cleanup_user_prompt_template": "user {raw}",
        },
    )
    assert r.status_code == 400
