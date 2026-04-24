"""Settings management endpoints."""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from app.services import users
from app.services.storage import UserDataStore, DEFAULT_DATA_DIR

router = APIRouter(tags=["settings"])


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


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings."""
    store = get_user_store(request)
    settings = store.get_settings()
    return settings.model_dump()


@router.patch("/settings")
async def update_settings(request: Request, req: UpdateSettingsRequest):
    """Update settings."""
    store = get_user_store(request)
    settings = store.update_settings(
        theme=req.theme,
        lm_studio_url=req.lm_studio_url,
        ollama_url=req.ollama_url,
        default_model=req.default_model,
        default_provider=req.default_provider,
        speech_model=req.speech_model,
        dictation_llm_cleanup_enabled=req.dictation_llm_cleanup_enabled,
        dictation_instructions=req.dictation_instructions,
        dictation_vocabulary=req.dictation_vocabulary,
    )
    return settings.model_dump()


@router.get("/version")
async def get_version():
    """Get the software version."""
    return {"version": "0.1.0"}
