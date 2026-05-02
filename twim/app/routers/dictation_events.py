"""SSE endpoint for dictation status updates."""
from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.services import users
from app.services.dictation_events import wait_for_events

router = APIRouter(tags=["dictation-events"])


@router.get("/dictation/events")
async def dictation_events(request: Request) -> EventSourceResponse:
    if not request.cookies.get("twim_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    session_user = request.cookies.get("twim_session") or ""
    if not users.get_user(session_user):
        raise HTTPException(status_code=404, detail="User not found")

    async def event_stream():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break
            # Do not block the asyncio loop: wait_for_events uses threading.Condition.wait.
            events, cursor = await asyncio.to_thread(
                wait_for_events, session_user, cursor, 5.0
            )
            if events:
                for event in events:
                    yield {"event": "dictation", "data": json.dumps(event)}
            else:
                yield {"event": "heartbeat", "data": json.dumps({"type": "heartbeat"})}

    return EventSourceResponse(event_stream())
