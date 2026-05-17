"""twim health endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(async_client: AsyncClient) -> None:
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
