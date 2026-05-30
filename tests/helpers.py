"""Shared helpers for tests."""


def attach_session_from_register(client, response):
    """Apply Set-Cookie from register/login onto the ASGI test client."""
    for name, value in response.cookies.items():
        client.cookies.set(name, value, domain="test", path="/")
