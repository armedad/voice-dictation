"""twim settings API tests."""

from __future__ import annotations

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
