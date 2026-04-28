"""FastAPI application for ai-frame - LLM App Skeleton Framework."""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
import asyncio
import threading
import sys
import json
import time

# Voice dictation MVP package root (parent of ai-frame): core/, platform_mac/, etc.
# Must run before routers that import `core` (dictation, speech-models, …).
VOICE_DICTATION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(VOICE_DICTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_DICTATION_ROOT))

from app.routers import auth, chat, models, settings, client_log, notifications, providers, dictation, dictation_events

# Directories
PROJECT_DIR = Path(__file__).parent.parent
USERS_DIR = PROJECT_DIR / "users"
LOGS_DIR = PROJECT_DIR / "logs"


def print_startup_banner():
    """Print a clear startup banner to logs."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    banner = f"""
================================================================================
  AI-FRAME - LLM App Skeleton Framework
  Time: {timestamp}
  Port: 8000
  URL:  http://localhost:8000
================================================================================
"""
    print(banner, flush=True)
    print(banner, file=sys.stderr, flush=True)


# Ensure directories exist
USERS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Print startup banner
print_startup_banner()

app = FastAPI(
    title="ai-frame",
    description="LLM App Skeleton Framework",
    version="0.1.0"
)

_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"


def _debug_emit(location: str, message: str, data: dict) -> None:
    # region agent log
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": "dictation-latency",
        "hypothesisId": "H_SERVER",
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except OSError:
        pass
    # endregion


def _debug_emit_custom(location: str, message: str, data: dict, run_id: str, hypothesis_id: str) -> None:
    # region agent log
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except OSError:
        pass
    # endregion


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
    if path == "/" or path == "/favicon.ico" or path.startswith("/static/"):
        t0 = time.time()
        # #region agent log
        _debug_emit(
            "app/main.py:web_middleware",
            "web request start",
            {
                "path": path,
                "method": request.method,
                "host": request.headers.get("host"),
                "scheme": request.url.scheme,
                "client": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        # #endregion
        response = await call_next(request)
        # #region agent log
        _debug_emit(
            "app/main.py:web_middleware",
            "web request end",
            {
                "path": path,
                "status": response.status_code,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "host": request.headers.get("host"),
                "scheme": request.url.scheme,
            },
        )
        # #endregion
        return response
    if path in ("/api/notifications", "/api/auth/logout", "/api/dictation/last-context"):
        t0 = time.time()
        loop_id = None
        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_id = None
        _debug_emit_custom(
            "app/main.py:api_middleware",
            "api request start",
            {
                "path": path,
                "method": request.method,
                "host": request.headers.get("host"),
                "scheme": request.url.scheme,
                "client": request.client.host if request.client else None,
                "tab_id": request.headers.get("x-twim-tab-id"),
                "loop_id": loop_id,
                "thread": threading.current_thread().name,
            },
            "server-http",
            "H_SERVER_HTTP",
        )
        response = await call_next(request)
        _debug_emit_custom(
            "app/main.py:api_middleware",
            "api request end",
            {
                "path": path,
                "status": response.status_code,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "tab_id": request.headers.get("x-twim-tab-id"),
                "loop_id": loop_id,
                "thread": threading.current_thread().name,
            },
            "server-http",
            "H_SERVER_HTTP",
        )
        return response
    return await call_next(request)


@app.on_event("startup")
async def _debug_startup_event() -> None:
    # #region agent log
    _debug_emit(
        "app/main.py:startup",
        "app startup event",
        {"thread": threading.current_thread().name},
    )
    # #endregion


@app.on_event("shutdown")
async def _debug_shutdown_event() -> None:
    # #region agent log
    _debug_emit(
        "app/main.py:shutdown",
        "app shutdown event",
        {"thread": threading.current_thread().name},
    )
    # #endregion

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
    # #region agent log
    _debug_emit(
        "app/main.py:root",
        "root request",
        {"thread": threading.current_thread().name},
    )
    # #endregion
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    # #region agent log
    _debug_emit(
        "app/main.py:health",
        "health request",
        {"thread": threading.current_thread().name},
    )
    # #endregion
    return {"status": "ok", "version": "0.1.0"}
