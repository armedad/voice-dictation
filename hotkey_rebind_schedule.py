"""Schedule hotkey rebind from the hotkey sidecar HTTP worker thread onto the right execution context."""
from __future__ import annotations

import logging
import sys
from typing import Callable

_LOG = logging.getLogger("hotkey_rebind_schedule")


def _safe_apply(apply: Callable[[], None]) -> None:
    try:
        apply()
    except Exception:
        _LOG.exception("Hotkey rebind failed")


def schedule_hotkey_rebind_from_http_thread(apply: Callable[[], None]) -> None:
    """
    Run ``apply`` where the platform hotkey stack expects it.

    macOS: main run loop via ``AppHelper.callAfter`` (HTTP server uses worker threads).
    Windows: same process; ``apply`` runs on the HTTP thread (``set_hotkeys`` is locked).
    """
    if sys.platform == "darwin":
        from PyObjCTools import AppHelper

        AppHelper.callAfter(lambda: _safe_apply(apply))
    else:
        # win32 and any other platform: direct call
        _safe_apply(apply)
