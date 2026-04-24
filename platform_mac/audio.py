from __future__ import annotations

import io
import wave

import numpy as np
import sounddevice as sd


def record_wav_bytes(duration_s: float, sample_rate: int = 16000) -> bytes:
    """Blocking capture from default input device; returns WAV bytes (mono int16)."""
    frames = int(duration_s * sample_rate)
    recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    audio = np.squeeze(recording, axis=1)
    audio_i16 = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())
    return buf.getvalue()
