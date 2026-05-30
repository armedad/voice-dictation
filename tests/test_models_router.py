"""Tests for twim.app.routers.models helpers."""

from __future__ import annotations

from app.routers.models import is_chat_model


def test_is_chat_model_excludes_embeddings() -> None:
    assert is_chat_model("gpt-4o") is True
    assert is_chat_model("text-embedding-3-small") is False
    assert is_chat_model("nomic-embed-text") is False
