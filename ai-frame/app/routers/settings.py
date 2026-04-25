"""Settings management endpoints."""
import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import users
from app.services.storage import UserDataStore, DEFAULT_DATA_DIR

router = APIRouter(tags=["settings"])


def _sync_hotkey_agent_target_user(store: UserDataStore, patch: dict[str, Any]) -> None:
    """Record which account last edited hotkeys so ``run_combined_app`` / hotkey_agent can default."""
    if not store.username:
        return
    if "dictation_hotkey_toggle" not in patch and "dictation_hotkey_cancel" not in patch:
        return
    users.ensure_users_dir()
    marker = users.USERS_DIR / ".hotkey_agent_target_username"
    marker.write_text(store.username.strip() + "\n", encoding="utf-8")


async def _notify_hotkey_sidecar_reload(username: str) -> None:
    """
    Best-effort loopback notify so macOS hotkey sidecar can rebind immediately.
    Falls back to file polling when sidecar is unreachable.
    """
    if not username:
        return
    try:
        ping_port = int(os.environ.get("VOICE_DICTATION_HOTKEY_PING_PORT", "18447"))
    except ValueError:
        ping_port = 18447
    url = f"http://127.0.0.1:{ping_port}/hotkeys/reload"
    try:
        async with httpx.AsyncClient(timeout=0.35) as client:
            await client.post(url, json={"username": username})
    except Exception:
        # Sidecar may be down; periodic file polling in the agent remains as fallback.
        return


def get_user_store(request: Request) -> UserDataStore:
    """Get the data store for the current user."""
    session_user = request.cookies.get("aiframe_session")
    if session_user:
        data_dir = users.get_user_data_dir(session_user)
        return UserDataStore(data_dir, session_user)
    return UserDataStore(DEFAULT_DATA_DIR)


class UpdateSettingsRequest(BaseModel):
    theme: Optional[str] = None
    lm_studio_url: Optional[str] = None
    ollama_url: Optional[str] = None
    default_model: Optional[str] = None
    default_provider: Optional[str] = None
    speech_model: Optional[str] = None
    dictation_llm_cleanup_enabled: Optional[bool] = None
    dictation_instructions: Optional[str] = None
    dictation_vocabulary: Optional[str] = None
    dictation_use_default_system_prompt: Optional[bool] = None
    dictation_custom_system_prompt_base: Optional[str] = None
    dictation_hotkey_toggle: Optional[dict[str, Any]] = None
    dictation_hotkey_cancel: Optional[dict[str, Any]] = None
    dictation_input_device_index: Optional[int] = None


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings."""
    store = get_user_store(request)
    settings = store.get_settings()
    return settings.model_dump()


@router.patch("/settings")
async def update_settings(request: Request, req: UpdateSettingsRequest):
    """Update settings (partial PATCH: only fields present in the JSON body)."""
    store = get_user_store(request)
    patch = req.model_dump(exclude_unset=True)

    if "dictation_input_device_index" in patch:
        v = patch["dictation_input_device_index"]
        if v is not None:
            if not isinstance(v, int) or v < 0:
                raise HTTPException(
                    status_code=400,
                    detail="dictation_input_device_index must be null or a non-negative integer.",
                )
            from core.portaudio_devices import valid_input_indices

            valid = valid_input_indices()
            if not valid:
                raise HTTPException(
                    status_code=400,
                    detail="No input microphones are available (PortAudio / sounddevice).",
                )
            if v not in valid:
                raise HTTPException(
                    status_code=400,
                    detail="That microphone is not available. Choose another device or System microphone.",
                )

    from core.hotkey_chord import parse_chord_or_raise

    for field in ("dictation_hotkey_toggle", "dictation_hotkey_cancel"):
        if field not in patch:
            continue
        val = patch[field]
        if val is not None:
            try:
                patch[field] = parse_chord_or_raise(val)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            store.ensure_hotkey_secret()

    settings = store.update_settings_patch(patch)
    _sync_hotkey_agent_target_user(store, patch)
    if "dictation_hotkey_toggle" in patch or "dictation_hotkey_cancel" in patch:
        await _notify_hotkey_sidecar_reload(store.username or "")
    return settings.model_dump()


@router.get("/version")
async def get_version():
    """Get the software version."""
    return {"version": "0.1.0"}
