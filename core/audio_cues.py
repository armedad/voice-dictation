from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

_CUE_SAMPLE_RATE = 44100
_CUE_VOLUME = 0.18
_cue_lock = threading.Lock()


def _tone(frequency_hz: float, duration_s: float) -> np.ndarray:
    frames = max(1, int(_CUE_SAMPLE_RATE * duration_s))
    t = np.arange(frames, dtype=np.float32) / float(_CUE_SAMPLE_RATE)
    return np.sin(2.0 * np.pi * frequency_hz * t).astype(np.float32)


def _envelope(audio: np.ndarray, attack_s: float = 0.01, release_s: float = 0.02) -> np.ndarray:
    if audio.size == 0:
        return audio
    out = np.copy(audio)
    attack = min(out.size, int(_CUE_SAMPLE_RATE * attack_s))
    release = min(out.size, int(_CUE_SAMPLE_RATE * release_s))
    if attack > 0:
        out[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
    if release > 0:
        out[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)
    return out


def _make_cue(tones_hz: tuple[float, ...], tone_duration_s: float = 0.07, gap_s: float = 0.02) -> np.ndarray:
    parts: list[np.ndarray] = []
    gap = np.zeros(max(1, int(_CUE_SAMPLE_RATE * gap_s)), dtype=np.float32)
    for i, freq in enumerate(tones_hz):
        parts.append(_envelope(_tone(freq, tone_duration_s)))
        if i < len(tones_hz) - 1:
            parts.append(gap)
    cue = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    return (cue * _CUE_VOLUME).astype(np.float32)


_START_CUE = _make_cue((660.0, 880.0))
_STOP_CUE = _make_cue((880.0, 660.0))


def _play_async(cue: np.ndarray) -> None:
    def _runner() -> None:
        with _cue_lock:
            try:
                sd.play(cue, samplerate=_CUE_SAMPLE_RATE, blocking=True)
            except Exception:
                # Best-effort UX hint only: never fail dictation if sound playback fails.
                return

    threading.Thread(target=_runner, name="dictation-cue", daemon=True).start()


def play_recording_start_cue() -> None:
    _play_async(_START_CUE)


def play_recording_stop_cue() -> None:
    _play_async(_STOP_CUE)
