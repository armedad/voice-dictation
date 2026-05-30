"""Shared timestamp helpers."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso_z() -> str:
    """UTC timestamp as ISO-8601 with ``Z`` suffix (matches legacy ``utcnow()`` format)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
