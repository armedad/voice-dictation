from __future__ import annotations

import asyncio
import os
from typing import Optional
import tempfile
from pathlib import Path

from ..models import AdapterEndpoint

_model_cache: dict[tuple[str, str, str], object] = {}


def _get_model(model_name: str) -> object:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            "Local transcription needs faster-whisper. Install: pip install faster-whisper"
        ) from e

    device = os.environ.get("VOICE_DICTATION_WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("VOICE_DICTATION_WHISPER_COMPUTE", "int8")
    key = (model_name, device, compute_type)
    if key not in _model_cache:
        _model_cache[key] = WhisperModel(
            model_name, device=device, compute_type=compute_type
        )
    return _model_cache[key]


def _transcribe_sync(
    wav_bytes: bytes,
    endpoint: AdapterEndpoint,
    initial_prompt: Optional[str] = None,
) -> str:
    model = _get_model(endpoint.model_name)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name
    try:
        kw: dict = {"vad_filter": True}
        lang = os.environ.get("VOICE_DICTATION_WHISPER_LANGUAGE", "").strip()
        if lang:
            kw["language"] = lang
        if initial_prompt and initial_prompt.strip():
            kw["initial_prompt"] = initial_prompt.strip()
        segments, _info = model.transcribe(tmp_path, **kw)
        parts = [s.text for s in segments]
        return "".join(parts).strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def transcribe_faster_whisper(
    wav_bytes: bytes,
    endpoint: AdapterEndpoint,
    initial_prompt: Optional[str] = None,
) -> str:
    """Local faster-whisper (CTranslate2). `model` is a size id (e.g. base, small, distil-large-v3)."""
    return await asyncio.to_thread(_transcribe_sync, wav_bytes, endpoint, initial_prompt)
