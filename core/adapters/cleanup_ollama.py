from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from ..models import AdapterEndpoint, DEFAULT_CLEANUP_SYSTEM_PROMPT


async def cleanup_ollama_chat(
    raw_transcript: str,
    endpoint: AdapterEndpoint,
    system_prompt: Optional[str] = None,
) -> str:
    """Local Ollama chat cleanup via POST /api/chat (no API key)."""
    base = endpoint.baseURL.rstrip("/")
    url = f"{base}/api/chat"
    sys_content = system_prompt or DEFAULT_CLEANUP_SYSTEM_PROMPT
    payload: dict[str, Any] = {
        "model": endpoint.model_name,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": raw_transcript},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        body = r.json()

    msg = body.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"Unexpected Ollama chat response: {json.dumps(body)[:800]}")
    return content.strip()
