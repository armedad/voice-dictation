"""Client-side logging endpoint - receives logs from frontend and writes to server log."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from datetime import datetime

router = APIRouter(tags=["logging"])

# Logs directory
PROJECT_DIR = Path(__file__).parent.parent.parent
LOGS_DIR = PROJECT_DIR / "logs"


def sanitize_for_console(text: str) -> str:
    """Remove or replace characters that can't be encoded by console."""
    try:
        return text.encode('cp1252', errors='replace').decode('cp1252')
    except Exception:
        return ''.join(c if ord(c) < 128 else '?' for c in text)


def write_to_log_file(level: str, message: str, data: Optional[dict] = None):
    """Write a log entry to the daily log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y%m%d")
    log_file = LOGS_DIR / f"aiframe_{today}.log"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    data_str = f" | {data}" if data else ""
    entry = f"[{timestamp}] [{level.upper()}] {message}{data_str}\n"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


class LogEntry(BaseModel):
    level: str
    message: str
    data: Optional[dict] = None


class LogBatch(BaseModel):
    logs: List[LogEntry]


@router.post("/log")
async def receive_client_logs(batch: LogBatch):
    """Receive logs from the frontend and print them to server console."""
    for entry in batch.logs:
        level = entry.level.upper()
        data_str = f" | {entry.data}" if entry.data else ""
        output = f"[CLIENT {level}] {entry.message}{data_str}"
        print(sanitize_for_console(output))
        
        # Also write to log file
        write_to_log_file(f"CLIENT_{level}", entry.message, entry.data)
    
    return {"received": len(batch.logs)}


@router.post("/log/single")
async def receive_single_log(entry: LogEntry):
    """Receive a single log entry from the frontend."""
    level = entry.level.upper()
    data_str = f" | {entry.data}" if entry.data else ""
    output = f"[CLIENT {level}] {entry.message}{data_str}"
    print(sanitize_for_console(output))
    
    write_to_log_file(f"CLIENT_{level}", entry.message, entry.data)
    
    return {"received": 1}
