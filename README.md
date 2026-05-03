# Voice dictation MVP (SuperWhisper-like)

Personal **macOS + Windows** loop: **hotkey → dictate → transcribe → LLM cleanup → inject at caret** — **Python shared core** + thin **platform_mac** / **platform_win** modules for hotkeys, tray, mic, and synthetic typing.

This folder implements the **feasibility plan**: written scope, stack choice, and a **runnable permissions spike** (no cloud APIs yet).

## Starter UI (twim — Python base)

[`twim/`](twim/) is the **in-repo** FastAPI + static JS app for **localhost settings** and provider/model UI. **Product direction:** grow dictation features here (or refactor into `apps/settings_server/`) under the same **Python** stack as [`docs/2026-04-23-stack-decision.md`](docs/2026-04-23-stack-decision.md).

## Configuration (model abstraction)

Transcription and cleanup use **separate** settings. See [`config/example-model-settings.json`](config/example-model-settings.json): top-level `transcription` vs `cleanup`. The **Python** process loads that shape (or an equivalent merged with twim settings); **secrets** belong in **OS stores** via `platform_*` modules, not long-term plaintext in JSON.

## Documents

- [MVP scope](docs/2026-04-23-mvp-scope.md) — start/stop/cancel shortcuts, menu bar + sounds, strict synthetic typing, **independently user-configured** transcription vs cleanup models/providers.
- [Stack decision](docs/2026-04-23-stack-decision.md) — **Python** shared core + **`platform_mac` / `platform_win`**; **localhost** settings (**twim**); **spike** mac lab only.
- [Permissions spike checklist](docs/2026-04-23-permissions-spike-checklist.md) — Browser, Slack, Terminal verification steps.

## One-shot install (macOS-friendly)

From [`coding/voice-dictation-mvp/`](.):

```bash
./install.sh              # venv, deps, PortAudio (brew), faster-whisper weights, ollama pull
./install.sh --help       # flags: --agent-only, --skip-ollama, --skip-whisper, --skip-twim, --with-spike, --recreate-venv
```

## Start settings server

```bash
./start.sh                      # ensures Ollama is up (curl + ollama serve if needed), then FastAPI
./start.sh --port 8765          # or: VOICE_DICTATION_PORT=8765 ./start.sh
./start.sh --skip-ollama-ensure # skip Ollama check/start
```

Ollama check uses `OLLAMA_HOST` / `OLLAMA_PORT` (default `127.0.0.1` / `11434`). Logs: `logs/ollama-serve.log`.

## Spike (run locally on your Mac)

```bash
cd spike
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 mac_injection_spike.py paste    # Accessibility + Cmd+V
python3 mac_injection_spike.py hotkey  # Input Monitoring + global Ctrl+Shift+0
python3 mac_injection_spike.py record  # Mic + save spike.wav + paste status
```

Do not edit the original Cursor plan file under `~/.cursor/plans/`; these artifacts are the implementation of that plan’s todos.

## Agent (dev — Python pipeline)

Portable **`core/`** and **`platform_mac/`** (mic WAV capture, `pynput` typing). **`platform_win/`** is stubbed.

**Default local stack** (see [`config/example-model-settings.json`](config/example-model-settings.json)):

- **Transcription:** **`faster_whisper`** (local [faster-whisper](https://github.com/SYSTRAN/faster-whisper); `model` e.g. `base`, `small`, `distil-large-v3`). Ollama does **not** expose a stable WAV→text API for general use, so STT is not routed through Ollama here.
- **Cleanup:** **`ollama_chat`** against **`http://127.0.0.1:11434`** — set `cleanup.model` to a model you have pulled (e.g. `llama3.2`, `mistral`). No API key.

Optional env: **`VOICE_DICTATION_WHISPER_DEVICE`** (`cpu` / `cuda`), **`VOICE_DICTATION_WHISPER_COMPUTE`** (e.g. `int8`, `float16`), **`VOICE_DICTATION_WHISPER_LANGUAGE`** (e.g. `en`). For cloud STT/cleanup instead, set `transcription.provider` to **`openai_compatible_audio`** and `cleanup.provider` to **`openai_compatible_chat`** and export **`OPENAI_API_KEY`**.

```bash
cd "coding/voice-dictation-mvp"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-agent.txt
ollama serve   # in another terminal, with your chat model pulled
python dictation_cli.py demo-wav /path/to/sample.wav
python dictation_cli.py record-once --seconds 4 --no-type
```

First run creates **`~/.voice-dictation/config.json`** from the example file if missing. To re-seed after we change defaults, delete that file and run again.

## Debug Logging

- The **Settings → Debug → Debug Flags** UI is the shared logging control plane for both frontend and backend debug traces.
- Frontend flags are persisted in per-user settings (`twim/users/<username>/settings.json` under `debug_flags`) and mirrored to localStorage only as a bootstrap/offline fallback.
- Backend debug traces now route through the same flag categories and write to the daily twim log (`twim/logs/twim_YYYYMMDD.log`).
- Strong-reason exceptions kept outside debug flags:
  - startup/boot banners emitted before user settings are available,
  - crash-path stderr messages where process-level visibility is required.

## Next build steps (not in spike)

1. **Agent + tray** (per OS): **Start**, **Stop & process**, and **Cancel** shortcuts; idle/recording **tray/menu bar state** + **start/stop sounds**; open **localhost settings** for **transcription** vs **cleanup** backends (user-picked models/endpoints/keys).
2. After **Stop & process**: audio → **transcription adapter** → **cleanup adapter** → **synthetic typing** only (**strict** — no paste fallback on failure).
3. Minimal logging and surfaced errors when a chosen provider, typing injection, or permissions fail.
