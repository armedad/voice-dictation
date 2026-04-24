# Permissions spike — verification checklist

**Date:** 2026-04-23  
**Spike code:** [`spike/mac_injection_spike.py`](../spike/mac_injection_spike.py)

Run from a terminal that you can grant permissions to (Terminal.app, iTerm, or the IDE’s integrated terminal—each has its own toggles).

## Setup

```bash
cd "coding/voice-dictation-mvp/spike"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## macOS settings

**System Settings → Privacy & Security**

1. **Accessibility** — enable for the app running Python (Terminal / Cursor / iTerm). Required for synthetic **Cmd+V** in `paste` and `record`.
2. **Input Monitoring** — enable for the same app. Required for **global hotkeys** with `pynput` in `hotkey` and `record`.
3. **Microphone** — enable for the same app. Required for **`record`**.

If a permission was previously denied, reset it under **Privacy & Security → [category] → remove app** and re-run the spike so macOS prompts again.

## Target app checks

For each app, focus a normal text field (not a password field).

### Browser (Chrome or Safari)

- Open a blank tab, focus the address bar or a Google search box.
- Run `python3 mac_injection_spike.py paste` and confirm the marker string appears.

### Slack

- Focus the message composer in a DM or channel.
- Run the same `paste` test.

### Terminal

- Focus the shell prompt in Terminal.app or iTerm.
- Run `paste` again. **Note:** Some terminal profiles consume Cmd+V differently or use bracketed paste; if paste fails, try another terminal or a plain `bash` window. This is expected variance, not necessarily a failed spike.

## Hotkey-only test

```bash
python3 mac_injection_spike.py hotkey
```

With focus in **another** app, press **Ctrl+Shift+0**. You should see a line printed in the terminal where the script runs. If not, re-check **Input Monitoring**.

## Mic + end-to-end injection test

```bash
python3 mac_injection_spike.py record
```

1. Focus a text field in Slack or Notes.
2. **Ctrl+Shift+9** to start recording; speak briefly.
3. **Ctrl+Shift+0** to stop. A `spike.wav` appears in the current directory and a short status string is pasted into the focused field.

This does **not** call STT or an LLM; it only validates mic capture + paste path.

## What this proves for the full MVP

- **Accessibility + pasteboard** path works for injection in your common apps.
- **Input Monitoring** path works for global capture keys.
- **Microphone** path works for short buffered capture.

Remaining MVP work: wire STT + LLM after the buffer is finalized, snapshot/restore clipboard if desired, and replace Ctrl+Shift+digits with a single hold-to-talk chord.
