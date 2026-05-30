"""FastAPI application for twim (voice dictation settings + API)."""
from __future__ import annotations
import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path
from datetime import datetime
import sys
import time

# Voice dictation MVP package root (parent of twim): core/, platform_mac/, etc.
# Must run before routers that import `core` (dictation, speech-models, …).
VOICE_DICTATION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(VOICE_DICTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_DICTATION_ROOT))

from core.default_twim_port import DEFAULT_TWIM_HTTP_PORT

from app.routers import (
    auth,
    chat,
    client_log,
    dictation,
    dictation_events,
    local_shutdown,
    models,
    notifications,
    providers,
    settings,
)
from app.services import users
from core.debug_flags_logging import log_system

# Directories
PROJECT_DIR = Path(__file__).parent.parent
USERS_DIR = users.USERS_DIR
_override_logs = os.environ.get("TWIM_LOGS_DIR")
LOGS_DIR = Path(_override_logs) if _override_logs else PROJECT_DIR / "logs"


def print_startup_banner():
    """Print a clear startup banner to logs."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    port = (os.environ.get("VOICE_DICTATION_PORT") or "").strip() or str(DEFAULT_TWIM_HTTP_PORT)
    banner = f"""
================================================================================
  twim — voice dictation settings + API
  Time: {timestamp}
  Port: {port}
  URL:  http://localhost:{port}
================================================================================
"""
    print(banner, flush=True)
    print(banner, file=sys.stderr, flush=True)


# Ensure directories exist
USERS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Print startup banner (skip in tests via TWIM_QUIET_STARTUP)
if not os.environ.get("TWIM_QUIET_STARTUP"):
    print_startup_banner()

app = FastAPI(
    title="twim",
    description="Voice dictation settings and cleanup API",
    version="0.1.0"
)


@app.on_event("startup")
async def _warm_dictation_runtime_caches() -> None:
    """Pre-build STT/cleanup endpoints per user so hotkey start stays off the critical path."""
    if os.environ.get("TWIM_QUIET_STARTUP"):
        return
    from app.services.dictation_runtime_cache import warm_all_dictation_runtime_caches

    asyncio.create_task(warm_all_dictation_runtime_caches())

def _debug_emit(location: str, message: str, data: dict) -> None:
    log_system(level="INFO", message=message, data={"location": location, **data})


@app.middleware("http")
async def _debug_dictation_requests(request: Request, call_next):
    path = request.url.path
    if path in (
        "/api/dictation/hotkey/toggle",
        "/api/dictation/hotkey/cancel",
        "/api/dictation/record-and-type",
    ):
        t0 = time.time()
        _debug_emit(
            "app/main.py:middleware",
            "request start",
            {"path": path, "method": request.method},
        )
        response = await call_next(request)
        _debug_emit(
            "app/main.py:middleware",
            "request end",
            {"path": path, "status": response.status_code, "elapsed_ms": int((time.time() - t0) * 1000)},
        )
        return response
    return await call_next(request)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(client_log.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(dictation.router, prefix="/api")
app.include_router(dictation_events.router, prefix="/api")
app.include_router(local_shutdown.router, prefix="/api")

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    """Browsers request /favicon.ico by default; serve the SVG asset (modern clients accept it)."""
    return FileResponse(
        STATIC_DIR / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/")
async def root():
    """Serve the main chat interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
