#!/usr/bin/env python3
"""Single-process launcher for Voice Dictation MVP (twim + optional global hotkeys).

Modes:
  Default (macOS / Windows): main thread = hotkey runtime; background thread = uvicorn (no reload).
  --skip-hotkey-agent: main thread = uvicorn only (--reload allowed for dev).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from core.debug_flags_logging import log_system
from core.default_twim_port import DEFAULT_TWIM_HTTP_PORT

def _debug_emit(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "combined-startup",
) -> None:
    log_system(
        level="INFO",
        message=message,
        data={
            "location": location,
            "run_id": run_id,
            "hypothesis_id": hypothesis_id,
            **data,
        },
    )


def main() -> None:
    # Enables POST /api/local/shutdown from the twim UI (loopback-only) to exit this process.
    os.environ["VOICE_DICTATION_COMBINED_LAUNCHER"] = "1"

    p = argparse.ArgumentParser(description="Single-process Voice Dictation MVP launcher.")
    p.add_argument("--port", type=int, default=DEFAULT_TWIM_HTTP_PORT)
    p.add_argument(
        "--skip-hotkey-agent",
        action="store_true",
        help="Run only the FastAPI app on the main thread (no global hotkeys).",
    )
    p.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn autoreload (only with --skip-hotkey-agent).",
    )
    args = p.parse_args()

    if args.reload and not args.skip_hotkey_agent:
        print("error: --reload is only supported with --skip-hotkey-agent.", file=sys.stderr)
        sys.exit(2)

    repo_root = Path(__file__).resolve().parent
    twim_app = repo_root / "twim"
    os.chdir(twim_app)
    twim_app_s = str(twim_app)
    if twim_app_s not in sys.path:
        sys.path.insert(0, twim_app_s)

    # #region agent log
    _debug_emit(
        hypothesis_id="H1",
        location="run_combined_app.py:main",
        message="cwd and sys.path head after twim setup",
        data={"cwd": os.getcwd(), "path0": sys.path[0] if sys.path else None},
    )
    # #endregion

    os.environ["VOICE_DICTATION_PORT"] = str(args.port)
    if args.skip_hotkey_agent:
        os.environ["VOICE_DICTATION_DISABLE_EMBEDDED_HOTKEY_AGENT"] = "1"
    else:
        os.environ.pop("VOICE_DICTATION_DISABLE_EMBEDDED_HOTKEY_AGENT", None)

    import uvicorn

    if args.skip_hotkey_agent:
        _debug_emit(
            hypothesis_id="H1",
            location="run_combined_app.py:main",
            message="uvicorn-only mode (main thread)",
            data={"port": args.port, "reload": args.reload},
        )
        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=args.port,
            reload=args.reload,
        )
        return

    if sys.platform not in ("darwin", "win32"):
        print(
            "error: embedded global hotkeys are only supported on macOS and Windows. "
            "Use --skip-hotkey-agent for API-only.",
            file=sys.stderr,
        )
        sys.exit(1)

    def _run_uvicorn() -> None:
        # #region agent log
        _debug_emit(
            hypothesis_id="H2",
            location="run_combined_app.py:_run_uvicorn",
            message="uvicorn thread entry",
            data={"cwd": os.getcwd()},
        )
        # #endregion
        try:
            uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, reload=False)
        except Exception as e:
            # #region agent log
            _debug_emit(
                hypothesis_id="H3",
                location="run_combined_app.py:_run_uvicorn",
                message="uvicorn.run failed",
                data={"exc_type": type(e).__name__, "exc": str(e)},
            )
            # #endregion
            raise

    t = threading.Thread(target=_run_uvicorn, name="uvicorn-server", daemon=True)
    t.start()

    if sys.platform == "darwin":
        from platform_mac.hotkey_agent import main as hotkey_main
    else:
        from platform_win.hotkey_agent import main as hotkey_main

    hotkey_main()


if __name__ == "__main__":
    main()
