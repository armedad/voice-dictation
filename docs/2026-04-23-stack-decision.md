# Voice dictation MVP — stack decision

**Date:** 2026-04-23 (updated: **Python** chosen as shared core)

## Decision summary

**Shared core:** **Python 3.11+** — orchestration (record → transcribe → cleanup → inject), adapter HTTP calls, config (Pydantic), and the **localhost FastAPI** pattern already used in [`ai-frame/`](../ai-frame/). Evolve that in-repo tree for dictation settings rather than adding a second language for v1.

**Target platforms:** **macOS and Windows**. Maximize portable Python; isolate **thin per-OS** modules (see layout below).

**Settings UI:** **Static web app** on **`http://127.0.0.1`** while settings are open: **loopback-only**, **short-lived server**, **auth token** on mutating routes ([MVP scope](2026-04-23-mvp-scope.md)). Reuse and slim **ai-frame** front/API toward dictation-only (two adapter panels; simplify auth if the agent is single-user).

**Suggested repo layout (incremental):**

- **`core/`** — config load/save, transcription/cleanup adapter interfaces, orchestrator, WAV/audio helpers, default cleanup prompt.
- **`platform_mac/`** — global hotkeys, mic capture, menu bar tray, synthetic typing (`pynput` + optional `pyobjc` for IME), Keychain for secrets.
- **`platform_win/`** — same responsibilities: hotkeys, mic, tray, `SendInput` typing (`pywin32` / `ctypes`), Credential Manager / DPAPI.
- **`ai-frame/`** — **starting point** for FastAPI + static JS; refactor over time into e.g. `apps/settings_server/` or keep as submodule-style folder imported by the agent entrypoint.

**Packaging:** **PyInstaller**, **Briefcase**, or **cx_Freeze** for `.app` / `.exe`; plan code signing when leaving dev-only installs.

**Python spike:** [`spike/`](../spike/) — **mac-only lab** for permission smoke tests, not the shipping runtime.

**Model routing:** Implement **TranscriptionService** / **CleanupService** (conceptual names) in **core**; JSON aligned with [`config/example-model-settings.json`](../config/example-model-settings.json); move API keys from ai-frame’s plain `providers.json` toward **OS secret stores** in platform modules.

## Why Python (and not Rust/Go for v1)

**ai-frame is already Python** — one toolchain, fast iteration, one venv for settings + orchestration. Rust/Go remains a **future** option if you need smaller binaries or stricter sandboxing; keep adapter **JSON contracts** stable if you ever port.

## Reminders (Python desktop)

**Pros:** FastAPI + `httpx` + optional local Whisper **subprocess**; large ecosystem.

**Cons / mitigations:** Packaged apps are **larger** than native Rust binaries — acceptable for MVP. Use **`pynput`** for portable hooks/typing; add **`pyobjc`** / **`pywin32`** only inside **`platform_*`** for hard cases. Users grant **Accessibility** / **Input Monitoring** (mac) or Windows automation permissions to the **packaged app**, not `python3` on PATH.

## Tradeoffs (honest)

- **Localhost settings:** Treat the mini-server as **security-sensitive** (bind, token, lifetime).
- **Cross-platform:** Two injection/hotkey implementations; **one** Python pipeline avoids duplicate business logic.

## Dependencies

- **Spike:** [`spike/requirements.txt`](../spike/requirements.txt) — mac lab only.
- **Product:** Lock with **uv** / **poetry** / `requirements.txt`; merge **ai-frame**’s [`ai-frame/requirements.txt`](../ai-frame/requirements.txt) into a top-level product lockfile as you unify packages; optional extras per adapter vendor.
