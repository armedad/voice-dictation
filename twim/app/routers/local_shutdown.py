"""Loopback-only process exit for the combined launcher (``run_combined_app`` / ``start.bat``)."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

router = APIRouter(tags=["local"])


def _require_loopback(request: Request) -> None:
    client = request.client
    host = (client.host if client else "") or ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Local shutdown accepts loopback only.")


def _exit_process() -> None:
    time.sleep(0.2)
    os._exit(0)


@router.post("/local/shutdown")
async def post_local_shutdown(request: Request, background_tasks: BackgroundTasks) -> dict[str, bool]:
    """End the Python process (combined app + hotkey sidecar). Response is sent before exit."""
    _require_loopback(request)
    flag = os.environ.get("VOICE_DICTATION_COMBINED_LAUNCHER", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        raise HTTPException(
            status_code=404,
            detail="Shutdown API is only enabled when started via run_combined_app / start script.",
        )
    background_tasks.add_task(_exit_process)
    return {"ok": True, "shutting_down": True}
