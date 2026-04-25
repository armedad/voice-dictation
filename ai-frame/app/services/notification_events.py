"""Lightweight per-user notification change bus for SSE."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _EventBuffer:
    events: list[dict[str, Any]] = field(default_factory=list)
    cond: threading.Condition = field(default_factory=threading.Condition)


_buffers: dict[str, _EventBuffer] = {}
_buffers_lock = threading.Lock()
_MAX_EVENTS = 200


def _get_buffer(username: str) -> _EventBuffer:
    with _buffers_lock:
        buf = _buffers.get(username)
        if buf is None:
            buf = _EventBuffer()
            _buffers[username] = buf
        return buf


def publish_notifications_changed(username: str) -> None:
    """Notify subscribers that notifications.json changed for this user."""
    payload: dict[str, Any] = {"type": "changed"}
    buf = _get_buffer(username)
    with buf.cond:
        buf.events.append(payload)
        if len(buf.events) > _MAX_EVENTS:
            buf.events = buf.events[-_MAX_EVENTS:]
        buf.cond.notify_all()


def wait_for_notification_events(
    username: str, cursor: int, timeout: float = 5.0
) -> tuple[list[dict[str, Any]], int]:
    buf = _get_buffer(username)
    with buf.cond:
        if cursor < len(buf.events):
            events = buf.events[cursor:]
            return events, len(buf.events)
        buf.cond.wait(timeout=timeout)
        events = buf.events[cursor:]
        return events, len(buf.events)
