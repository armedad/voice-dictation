"""FastAPI application for ai-frame - LLM App Skeleton Framework."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
import sys

# Voice dictation MVP package root (parent of ai-frame): core/, platform_mac/, etc.
# Must run before routers that import `core` (dictation, speech-models, …).
VOICE_DICTATION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(VOICE_DICTATION_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_DICTATION_ROOT))

from app.routers import auth, chat, models, settings, client_log, notifications, providers, dictation

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

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(client_log.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(dictation.router, prefix="/api")

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the main chat interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
