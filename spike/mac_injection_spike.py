#!/usr/bin/env python3
"""
macOS permissions spike for voice-dictation MVP.

Exercises:
  - Global hotkey (Input Monitoring when using pynput hooks)
  - Clipboard + synthetic Cmd+V (Accessibility)
  - Optional short WAV capture (Microphone)

Usage (from repo root or this directory):
  python3 mac_injection_spike.py hotkey
  python3 mac_injection_spike.py paste
  python3 mac_injection_spike.py record   # uses default mic; saves spike.wav in cwd

System Settings → Privacy & Security:
  - Accessibility: Terminal or your Python IDE must be enabled for `paste`.
  - Microphone: required for `record`.
  - Input Monitoring: often required for `hotkey` / `record` global listeners.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path


def _clipboard_set(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _paste_via_cmd_v() -> None:
    from pynput.keyboard import Controller, Key

    kb = Controller()
    with kb.pressed(Key.cmd):
        kb.tap("v")


def cmd_paste() -> None:
    """After Accessibility is granted, inserts text at the focused caret."""
    print("Focus a text field, then press Enter here to paste test text…", flush=True)
    try:
        input()
    except EOFError:
        print("No stdin; pasting in 3 seconds…", flush=True)
        time.sleep(3)
    marker = "[voice-dictation-mvp spike] paste OK — if you see this, Accessibility + Cmd+V works."
    _clipboard_set(marker)
    time.sleep(0.05)
    _paste_via_cmd_v()
    print("Done. Check the focused field for the marker text.", flush=True)


def _key_is_digit(key: object, digit: str) -> bool:
    """Best-effort digit match for Ctrl+Shift+digit combos (layout-dependent)."""
    from pynput import keyboard

    if not isinstance(key, keyboard.KeyCode):
        return False
    ch = key.char
    if ch == digit:
        return True
    vk = getattr(key, "vk", None)
    # macOS kVK_ANSI_0 = 0x1D (29), kVK_ANSI_9 = 0x19 (25) — common for US QWERTY
    if digit == "0" and vk == 29:
        return True
    if digit == "9" and vk == 25:
        return True
    return False


def cmd_hotkey() -> None:
    """Prints when Ctrl+Shift+0 is pressed — validates Input Monitoring for pynput."""
    from pynput import keyboard

    combo = {"ctrl": False, "shift": False}

    def update_modifiers(key: keyboard.Key | keyboard.KeyCode, pressed: bool) -> None:
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            combo["ctrl"] = pressed
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            combo["shift"] = pressed

    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == keyboard.Key.esc:
            print("ESC — exiting.", flush=True)
            return False
        if isinstance(key, keyboard.Key):
            update_modifiers(key, True)
        if combo["ctrl"] and combo["shift"] and _key_is_digit(key, "0"):
            print("Hotkey Ctrl+Shift+0 detected — Input Monitoring path works.", flush=True)

    def on_release(key: keyboard.Key | keyboard.KeyCode) -> None:
        if isinstance(key, keyboard.Key):
            update_modifiers(key, False)

    print(
        "Listening for Ctrl+Shift+0 anywhere (try it in another app). "
        "Press ESC in this terminal to quit.\n"
        "If nothing fires, enable Input Monitoring for this terminal/IDE.",
        flush=True,
    )
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


def cmd_record() -> None:
    """Hold-to-release style: Ctrl+Shift+9 starts recording; Ctrl+Shift+0 stops and saves spike.wav."""
    import numpy as np
    import sounddevice as sd

    from pynput import keyboard

    state = {"recording": False, "frames": []}
    sample_rate = 16000

    def flush_wav(path: Path, frames: list, sr: int) -> None:
        if not frames:
            return
        audio = np.concatenate(frames, axis=0)
        audio_i16 = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio_i16.tobytes())

    def audio_callback(indata, _frames, _time, status) -> None:
        if status:
            print(status, file=sys.stderr, flush=True)
        if state["recording"]:
            state["frames"].append(indata.copy())

    stream = sd.InputStream(
        channels=1,
        samplerate=sample_rate,
        dtype="float32",
        callback=audio_callback,
    )

    combo = {"ctrl": False, "shift": False}

    def mod_pressed(key: keyboard.Key, pressed: bool) -> None:
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            combo["ctrl"] = pressed
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            combo["shift"] = pressed

    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == keyboard.Key.esc:
            print("ESC — exiting.", flush=True)
            return False
        if isinstance(key, keyboard.Key):
            mod_pressed(key, True)
        if combo["ctrl"] and combo["shift"]:
            if _key_is_digit(key, "9"):
                state["frames"].clear()
                state["recording"] = True
                print("Recording… (Ctrl+Shift+0 to stop)", flush=True)
            elif _key_is_digit(key, "0") and state["recording"]:
                state["recording"] = False
                out = Path.cwd() / "spike.wav"
                flush_wav(out, state["frames"], sample_rate)
                msg = f"[voice-dictation-mvp spike] saved {out} ({len(state['frames'])} buffers)"
                print(msg, flush=True)
                _clipboard_set(msg)
                time.sleep(0.05)
                _paste_via_cmd_v()

    def on_release(key: keyboard.Key | keyboard.KeyCode) -> None:
        if isinstance(key, keyboard.Key):
            mod_pressed(key, False)

    print(
        "Mic spike: Ctrl+Shift+9 start, Ctrl+Shift+0 stop → writes spike.wav and pastes status.\n"
        "Grant Microphone + Input Monitoring + Accessibility to this app.\n"
        "ESC in this terminal to quit.",
        flush=True,
    )
    with stream:
        stream.start()
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("paste", help="Clipboard + Cmd+V test")
    sub.add_parser("hotkey", help="Global Ctrl+Shift+0 listener")
    sub.add_parser("record", help="Ctrl+Shift+9/0 mic capture + paste status")
    args = parser.parse_args()
    if args.command == "paste":
        cmd_paste()
    elif args.command == "hotkey":
        cmd_hotkey()
    elif args.command == "record":
        cmd_record()


if __name__ == "__main__":
    main()
