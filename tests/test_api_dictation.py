"""twim dictation API tests (no mic / hotkey sidecar)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from helpers import attach_session_from_register


async def _register_with_model(async_client: AsyncClient, *, cleanup_enabled: bool) -> None:
    r = await async_client.post(
        "/api/auth/register",
        json={
            "username": "dictuser",
            "password": "secret",
            "display_name": "Dict User",
        },
    )
    assert r.status_code == 200
    attach_session_from_register(async_client, r)
    patch_r = await async_client.patch(
        "/api/settings",
        json={
            "default_provider": "ollama",
            "default_model": "llama3.2",
            "dictation_llm_cleanup_enabled": cleanup_enabled,
        },
    )
    assert patch_r.status_code == 200


async def test_prompt_defaults_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get("/api/dictation/prompt-defaults")
    assert r.status_code == 401


async def test_prompt_defaults(async_client: AsyncClient) -> None:
    await _register_with_model(async_client, cleanup_enabled=True)
    from core.models import (
        DEFAULT_CLEANUP_SYSTEM_PROMPT,
        DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE,
    )

    r = await async_client.get("/api/dictation/prompt-defaults")
    assert r.status_code == 200
    body = r.json()
    assert body["default_cleanup_base_prompt"] == DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()
    assert (
        body["default_cleanup_system_prompt_template"]
        == DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE.strip()
    )


async def test_cleanup_text_unauthenticated(async_client: AsyncClient) -> None:
    r = await async_client.post(
        "/api/dictation/cleanup-text",
        json={"text": "hello"},
    )
    assert r.status_code == 401


async def test_cleanup_text_empty_body(async_client: AsyncClient) -> None:
    await _register_with_model(async_client, cleanup_enabled=True)
    r = await async_client.post("/api/dictation/cleanup-text", json={"text": ""})
    assert r.status_code == 422


async def test_cleanup_text_with_mocked_pipeline(async_client: AsyncClient) -> None:
    await _register_with_model(async_client, cleanup_enabled=True)
    with patch(
        "core.orchestrator.run_pipeline",
        new_callable=AsyncMock,
        return_value="cleaned",
    ) as mock_pipeline:
        r = await async_client.post(
            "/api/dictation/cleanup-text",
            json={"text": "hello world"},
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "text": "cleaned"}
    mock_pipeline.assert_awaited_once()
    assert mock_pipeline.await_args.kwargs["skip_llm_cleanup"] is False
    assert mock_pipeline.await_args.kwargs["raw_transcript_override"] == "hello world"


async def test_cleanup_text_cleanup_disabled(async_client: AsyncClient) -> None:
    await _register_with_model(async_client, cleanup_enabled=False)
    with patch(
        "core.orchestrator.run_pipeline",
        new_callable=AsyncMock,
        return_value="hello world",
    ) as mock_pipeline:
        r = await async_client.post(
            "/api/dictation/cleanup-text",
            json={"text": "hello world"},
        )
    assert r.status_code == 200
    assert r.json()["text"] == "hello world"
    assert mock_pipeline.await_args.kwargs["skip_llm_cleanup"] is True
