"""Notification endpoints for push notifications."""
import asyncio
import threading
import time
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from typing import Optional

from app.services import users
from app.services.notification_events import wait_for_notification_events
from app.services.storage import UserDataStore, DEFAULT_DATA_DIR

router = APIRouter(tags=["notifications"])


def get_user_store(request: Request) -> UserDataStore:
    """Get the data store for the current user."""
    session_user = request.cookies.get("aiframe_session")
    if session_user:
        data_dir = users.get_user_data_dir(session_user)
        return UserDataStore(data_dir, session_user)
    return UserDataStore(DEFAULT_DATA_DIR)


class AddNotificationRequest(BaseModel):
    type: str
    message: str
    source: Optional[str] = None
    details: Optional[str] = None


@router.get("/notifications/stream")
async def notifications_stream(request: Request) -> EventSourceResponse:
    """SSE: notification list changes (client should refetch GET /notifications)."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    session_user = request.cookies.get("aiframe_session") or ""
    if not users.get_user(session_user):
        raise HTTPException(status_code=404, detail="User not found")

    async def event_stream():
        cursor = 0
        while True:
            if await request.is_disconnected():
                break
            # Do not block the asyncio loop: wait uses threading.Condition.wait.
            events, cursor = await asyncio.to_thread(
                wait_for_notification_events, session_user, cursor, 5.0
            )
            if events:
                for event in events:
                    yield {"event": "notifications", "data": json.dumps(event)}
            else:
                yield {"event": "heartbeat", "data": json.dumps({"type": "heartbeat"})}

    return EventSourceResponse(event_stream())


@router.get("/notifications")
async def list_notifications(request: Request):
    """List user notifications (undismissed first)."""
    # #region agent log
    try:
        log_line = json.dumps(
            {
                "sessionId": "55f014",
                "runId": "server-notifications",
                "hypothesisId": "H_SERVER_HTTP",
                "location": "notifications.py:list_notifications",
                "message": "notifications request start",
                "data": {
                    "has_cookie": bool(request.cookies.get("aiframe_session")),
                    "thread": threading.current_thread().name,
                    "loop_id": id(asyncio.get_running_loop()),
                    "tab_id": request.headers.get("x-twim-tab-id"),
                },
                "timestamp": int(time.time() * 1000),
            },
            ensure_ascii=True,
        )
        with open("/Users/chee/zapier ai project/.cursor/debug-55f014.log", "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except OSError:
        pass
    # #endregion
    store = get_user_store(request)
    notifications = store.get_notifications()
    notifications.sort(key=lambda n: (n.dismissed, n.created_at))
    # #region agent log
    try:
        log_line = json.dumps(
            {
                "sessionId": "55f014",
                "runId": "server-notifications",
                "hypothesisId": "H_SERVER_HTTP",
                "location": "notifications.py:list_notifications",
                "message": "notifications request end",
                "data": {
                    "count": len(notifications),
                    "thread": threading.current_thread().name,
                    "loop_id": id(asyncio.get_running_loop()),
                    "tab_id": request.headers.get("x-twim-tab-id"),
                },
                "timestamp": int(time.time() * 1000),
            },
            ensure_ascii=True,
        )
        with open("/Users/chee/zapier ai project/.cursor/debug-55f014.log", "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except OSError:
        pass
    # #endregion
    return {"notifications": [n.model_dump() for n in notifications]}


@router.post("/notifications")
async def add_notification(request: Request, req: AddNotificationRequest):
    """Add a notification for the current user."""
    store = get_user_store(request)
    notif = store.add_notification(req.type, req.message, source=req.source, details=req.details)
    return {"notification": notif.model_dump()}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, request: Request):
    """Dismiss a notification."""
    store = get_user_store(request)
    success = store.dismiss_notification(notification_id)
    return {"success": success}


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str, request: Request):
    """Delete a notification permanently."""
    store = get_user_store(request)
    success = store.delete_notification(notification_id)
    return {"success": success}


@router.post("/notifications/dismiss-all")
async def dismiss_all_notifications(request: Request):
    """Dismiss all notifications for the current user."""
    store = get_user_store(request)
    count = store.dismiss_all_notifications()
    return {"success": True, "dismissed_count": count}


@router.delete("/notifications")
async def delete_all_notifications(request: Request):
    """Delete all notifications for the current user."""
    store = get_user_store(request)
    count = store.delete_all_notifications()
    return {"success": True, "deleted_count": count}
