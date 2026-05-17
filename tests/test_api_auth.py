"""twim auth API tests."""

from __future__ import annotations

from httpx import AsyncClient

from helpers import attach_session_from_register


async def test_has_users_empty(async_client: AsyncClient) -> None:
    r = await async_client.get("/api/auth/has-users")
    assert r.status_code == 200
    assert r.json()["has_users"] is False


async def test_register_and_me(async_client: AsyncClient) -> None:
    r = await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "secret",
            "display_name": "Test User",
        },
    )
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"
    attach_session_from_register(async_client, r)

    me = await async_client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["logged_in"] is True
    assert body["username"] == "testuser"


async def test_login_failure(async_client: AsyncClient) -> None:
    r = await async_client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    assert r.status_code == 401
