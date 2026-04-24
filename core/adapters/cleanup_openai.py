from __future__ import annotations

from typing import Optional

import httpx

from ..models import AdapterEndpoint, DEFAULT_CLEANUP_SYSTEM_PROMPT


async def cleanup_openai_chat(
    raw_transcript: str,
    endpoint: AdapterEndpoint,
    api_key: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """OpenAI-compatible chat completion for cleanup (optional API key for local LM Studio)."""
    base = endpoint.baseURL.rstrip("/")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    sys_content = system_prompt or DEFAULT_CLEANUP_SYSTEM_PROMPT
    payload = {
        "model": endpoint.model_name,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": raw_transcript},
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        body = r.json()

    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected chat response: {body!r}") from e
