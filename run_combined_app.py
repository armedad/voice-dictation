#!/usr/bin/env python3
"""Run ai-frame + macOS hotkeys in one process.

Main thread: platform_mac.hotkey_agent.main() (Carbon event pump)
Background thread: uvicorn app.main:app
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

# #region agent log
_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"


def _debug_emit(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "combined-startup",
) -> None:
    line = json.dumps(
        {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        },
        ensure_ascii=True,
    )
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# #endregion


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent
    ai_frame = repo_root / "ai-frame"
    # start.sh cds to ai-frame for plain uvicorn; combined mode runs this script from repo
    # root so sys.path[0] is repo root — uvicorn cannot import app.* unless ai-frame is on path.
    os.chdir(ai_frame)
    ai_frame_s = str(ai_frame)
    if ai_frame_s not in sys.path:
        sys.path.insert(0, ai_frame_s)

    # #region agent log
    _debug_emit(
        hypothesis_id="H1",
        location="run_combined_app.py:main",
        message="cwd and sys.path head after ai-frame setup",
        data={"cwd": os.getcwd(), "path0": sys.path[0] if sys.path else None},
    )
    # #endregion

    os.environ["VOICE_DICTATION_PORT"] = str(args.port)

    def _run_uvicorn() -> None:
        # #region agent log
        _debug_emit(
            hypothesis_id="H2",
            location="run_combined_app.py:_run_uvicorn",
            message="uvicorn thread entry",
            data={"cwd": os.getcwd()},
        )
        # #endregion
        import uvicorn

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

    from platform_mac.hotkey_agent import main as hotkey_main

    hotkey_main()


if __name__ == "__main__":
    main()
