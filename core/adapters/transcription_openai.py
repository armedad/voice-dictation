from __future__ import annotations

import io

import httpx

from ..models import AdapterEndpoint


async def transcribe_openai_whisper(
    wav_bytes: bytes,
    filename: str,
    endpoint: AdapterEndpoint,
    api_key: str,
) -> str:
    """OpenAI-compatible audio transcription (multipart POST .../audio/transcriptions)."""
    if not api_key:
        raise ValueError("Missing API key for transcription (env OPENAI_API_KEY or VOICE_DICTATION_TRANSCRIPTION_API_KEY)")

    base = endpoint.baseURL.rstrip("/")
    url = f"{base}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    files = {"file": (filename, io.BytesIO(wav_bytes), "audio/wav")}
    data = {"model": endpoint.model_name}

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, data=data, files=files)
        r.raise_for_status()
        body = r.json()
    text = body.get("text")
    if not isinstance(text, str):
        raise RuntimeError(f"Unexpected transcription response: {body!r}")
    return text.strip()
