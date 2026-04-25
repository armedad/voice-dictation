#!/usr/bin/env python3
"""Legacy entrypoint for a standalone hotkey-only process.

On macOS, use a single process instead: ``./start.sh`` or ``python run_combined_app.py``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "darwin" and not os.environ.get("VOICE_DICTATION_ALLOW_STANDALONE_HOTKEY_AGENT"):
    print(
        "run_hotkey_agent.py is disabled on macOS (use one process: ./start.sh or "
        "python run_combined_app.py).\n"
        "To run this script anyway: export VOICE_DICTATION_ALLOW_STANDALONE_HOTKEY_AGENT=1",
        file=sys.stderr,
    )
    sys.exit(2)

if sys.platform == "darwin":
    from platform_mac.hotkey_agent import main

    main()
else:
    from platform_win.hotkey_agent import main

    main()
