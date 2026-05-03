#!/usr/bin/env python3
"""
Dictation pipeline dev CLI (no web server).

Run from `coding/voice-dictation-mvp/` after:
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements-agent.txt

Default config uses local faster-whisper + Ollama (no API keys). For OpenAI adapters,
set OPENAI_API_KEY (or per-step VOICE_DICTATION_*_API_KEY). First run seeds
~/.voice-dictation/config.json from config/example-model-settings.json if missing.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def cmd_demo_wav(wav_path: Path) -> str:
    from core.orchestrator import run_pipeline

    data = wav_path.read_bytes()
    return await run_pipeline(data, wav_filename=wav_path.name)


async def cmd_record_once(seconds: float, do_type: bool) -> None:
    from core.orchestrator import run_pipeline

    if sys.platform != "darwin":
        print("record-once is only wired for macOS today; use demo-wav on other OSes.")
        sys.exit(1)

    from platform_mac.audio import record_wav_bytes
    from platform_mac.typing_inject import TypingInjectionError, type_text_strict

    print(f"Recording {seconds}s from default microphone…", flush=True)
    wav = record_wav_bytes(seconds)
    print("Transcribing + cleaning…", flush=True)
    text = await run_pipeline(wav, "dictation.wav")
    print("--- result ---\n", text, "\n--------------", flush=True)
    if do_type:
        print("Typing at focused field (Accessibility required)…", flush=True)
        try:
            type_text_strict(text)
        except TypingInjectionError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo-wav", help="Run STT+cleanup on a WAV file; print only")
    p_demo.add_argument("wav_path", type=Path)

    p_rec = sub.add_parser(
        "record-once",
        help="macOS: record N seconds, run pipeline, print; optionally type into focused app",
    )
    p_rec.add_argument("--seconds", type=float, default=5.0)
    p_rec.add_argument("--no-type", action="store_true", help="Skip synthetic typing")

    args = parser.parse_args()
    if args.command == "demo-wav":
        text = asyncio.run(cmd_demo_wav(args.wav_path))
        print(text)
    elif args.command == "record-once":
        asyncio.run(cmd_record_once(args.seconds, do_type=not args.no_type))


if __name__ == "__main__":
    main()
