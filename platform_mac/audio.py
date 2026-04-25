from __future__ import annotations

import io
import threading
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


def record_wav_bytes_interruptible(
    duration_s: float | None,
    cancel_event: threading.Event,
    *,
    stop_event: threading.Event | None = None,
    sample_rate: int = 16000,
    chunk_s: float = 0.25,
) -> tuple[bytes, bool, bool]:
    """
    Record mono WAV while polling ``cancel_event`` between reads.

    Uses a single ``sounddevice.InputStream`` for the whole capture so macOS shows one
    continuous microphone session (avoids flashing from repeated ``sd.rec`` open/close).

    Returns ``(wav_bytes, cancelled, stopped)``.
    - ``cancelled`` means the cancel event fired (discard recording).
    - ``stopped`` means the stop event fired (finish recording and process audio).
    """
    if not isinstance(cancel_event, threading.Event):
        raise TypeError("cancel_event must be threading.Event")

    n_target = int(duration_s * sample_rate) if duration_s and duration_s > 0 else None
    block_frames = max(1, int(chunk_s * sample_rate))
    parts: list[np.ndarray] = []
    n_read = 0

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocksize=block_frames,
    ) as stream:
        while n_target is None or n_read < n_target:
            if cancel_event.is_set():
                return b"", True, False
            if stop_event is not None and stop_event.is_set():
                break
            need = block_frames if n_target is None else min(block_frames, n_target - n_read)
            data, _overflowed = stream.read(need)
            if data is None or len(data) == 0:
                continue
            arr = np.asarray(data, dtype=np.float32)
            parts.append(np.squeeze(arr, axis=1))
            n_read += arr.shape[0]

    if cancel_event.is_set():
        return b"", True, False
    if not parts:
        return b"", stop_event is not None and stop_event.is_set(), stop_event is not None and stop_event.is_set()

    audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
    audio_i16 = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())
    return buf.getvalue(), False, stop_event is not None and stop_event.is_set()
