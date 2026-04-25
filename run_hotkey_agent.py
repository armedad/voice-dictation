#!/usr/bin/env python3
"""Entrypoint for the global dictation hotkey sidecar (platform-specific)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "darwin":
    from platform_mac.hotkey_agent import main

    main()
else:
    from platform_win.hotkey_agent import main

    main()
