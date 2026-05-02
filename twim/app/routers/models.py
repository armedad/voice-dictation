"""Model listing endpoints."""
import httpx
from fastapi import APIRouter, Request
from pathlib import Path

from app.services import users, ollama, lm_studio, providers_config
from app.services.storage import UserDataStore, DEFAULT_DATA_DIR

router = APIRouter(tags=["models"])

# Patterns to filter out non-chat models
EXCLUDED_PATTERNS = [
    "embed",
    "embedding",
    "nomic",
    "bge-",
    "e5-",
    "gte-",
]


def is_chat_model(model_id: str) -> bool:
    """Check if a model is a chat model (not an embedding model)."""
    model_lower = model_id.lower()
    for pattern in EXCLUDED_PATTERNS:
        if pattern in model_lower:
            return False
    return True


def get_user_store(request: Request) -> UserDataStore:
    """Get the data store for the current user."""
    session_user = request.cookies.get("twim_session")
    if session_user:
        data_dir = users.get_user_data_dir(session_user)
        return UserDataStore(data_dir, session_user)
    return UserDataStore(DEFAULT_DATA_DIR)


def get_user_data_dir(request: Request) -> Path:
    """Get the data directory for the current user."""
    session_user = request.cookies.get("twim_session")
    if session_user:
        return users.get_user_data_dir(session_user)
    return DEFAULT_DATA_DIR


@router.get("/models")
async def list_models(request: Request):
    """List all available models grouped by provider."""
    store = get_user_store(request)
    settings = store.get_settings()
    data_dir = get_user_data_dir(request)
    
    # Load provider config
    config = providers_config.load_providers(data_dir)
    
    groups = []
    errors: list[dict] = []

    # LM Studio models (if enabled)
    if config.local.get("enabled", True):
        try:
            # Use settings.json as primary source for URLs
            lm_url = settings.lm_studio_url
            lm_models = await lm_studio.list_models(lm_url)
            chat_models = [
                {"id": m.get("id"), "name": m.get("id")}
                for m in lm_models
                if m.get("id") and is_chat_model(m.get("id"))
            ]
            if chat_models:
                groups.append({
                    "provider": "local",
                    "name": "Local (LM Studio)",
                    "models": chat_models
                })
        except Exception as e:
            print(f"[Models] Failed to load LM Studio models: {e}")
            errors.append({"provider": "lm_studio", "detail": str(e)})

    # Ollama models (if enabled)
    if config.local.get("ollama_enabled", True):
        try:
            # Use settings.json as primary source for URLs
            ollama_url = settings.ollama_url
            ollama_models = await ollama.list_models(ollama_url)
            chat_models = [
                {"id": m.get("model") or m.get("name"), "name": m.get("model") or m.get("name")}
                for m in ollama_models
                if (m.get("model") or m.get("name")) and is_chat_model(m.get("model") or m.get("name"))
            ]
            if chat_models:
                groups.append({
                    "provider": "ollama",
                    "name": "Ollama",
                    "models": chat_models
                })
        except Exception as e:
            print(f"[Models] Failed to load Ollama models: {e}")
            errors.append({"provider": "ollama", "detail": str(e)})

    # Cloud providers (if configured and enabled)
    for provider_id, provider in config.providers.items():
        if provider.api_key and provider.enabled and provider.models:
            groups.append({
                "provider": provider_id,
                "name": provider.name,
                "models": [{"id": m, "name": m} for m in provider.models]
            })
    
    return {
        "groups": groups,
        "default": {
            "provider": settings.default_provider or "ollama",
            "model": settings.default_model,
        },
        "errors": errors,
    }


def _speech_models_default(settings, cfg) -> dict:
    """Default STT selection for UI (provider + model id)."""
    sm = (settings.speech_model or "").strip()
    if sm:
        if ":" in sm:
            p, _, m = sm.partition(":")
            return {
                "provider": (p or "faster_whisper").strip(),
                "model": (m or "").strip() or cfg.transcription.model_name,
            }
        return {"provider": "faster_whisper", "model": sm}
    tp = (cfg.transcription.provider or "").strip().lower()
    if tp in ("faster_whisper", "local_faster_whisper", "faster-whisper"):
        return {
            "provider": "faster_whisper",
            "model": cfg.transcription.model_name,
        }
    return {
        "provider": "openai_compatible_audio",
        "model": cfg.transcription.model_name,
    }


@router.get("/speech-models")
async def list_speech_models(request: Request):
    """Speech-to-text models: local Whisper sizes + remote models when configured."""
    from core.config import api_key_for_transcription, load_config
    from core.whisper_catalog import FASTER_WHISPER_MODEL_IDS

    store = get_user_store(request)
    settings = store.get_settings()
    cfg = load_config()

    groups: list[dict] = [
        {
            "provider": "faster_whisper",
            "name": "Local (faster-whisper)",
            "models": [{"id": m, "name": m} for m in FASTER_WHISPER_MODEL_IDS],
        }
    ]
    errors: list[dict] = []

    tp = (cfg.transcription.provider or "").strip().lower()
    if tp in ("openai_compatible_audio", "openai", "openai_whisper"):
        base = (cfg.transcription.baseURL or "").rstrip("/")
        key = api_key_for_transcription()
        if base and key:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(
                        f"{base}/models",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    r.raise_for_status()
                    body = r.json()
                    rows = body.get("data") or []
                    remote: list[dict] = []
                    for row in rows:
                        mid = row.get("id")
                        if not mid or not isinstance(mid, str):
                            continue
                        ml = mid.lower()
                        if "whisper" in ml or "transcribe" in ml:
                            remote.append({"id": mid, "name": mid})
                    if remote:
                        groups.append(
                            {
                                "provider": "openai_compatible_audio",
                                "name": "Remote (OpenAI-compatible STT)",
                                "models": remote,
                            }
                        )
            except Exception as e:
                errors.append({"provider": "openai_compatible_audio", "detail": str(e)})

    return {
        "groups": groups,
        "default": _speech_models_default(settings, cfg),
        "errors": errors,
    }


@router.get("/models/status")
async def check_providers_status(request: Request):
    """Check status of local providers."""
    store = get_user_store(request)
    settings = store.get_settings()
    
    status = {}
    
    # Check LM Studio
    try:
        models = await lm_studio.list_models(settings.lm_studio_url)
        status["lm_studio"] = {
            "connected": True,
            "url": settings.lm_studio_url,
            "model_count": len(models)
        }
    except Exception as e:
        status["lm_studio"] = {
            "connected": False,
            "url": settings.lm_studio_url,
            "error": str(e)
        }
    
    # Check Ollama
    try:
        models = await ollama.list_models(settings.ollama_url)
        status["ollama"] = {
            "connected": True,
            "url": settings.ollama_url,
            "model_count": len(models)
        }
    except Exception as e:
        status["ollama"] = {
            "connected": False,
            "url": settings.ollama_url,
            "error": str(e)
        }
    
    return status
