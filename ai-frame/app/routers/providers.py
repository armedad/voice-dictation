"""Provider management endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from app.services import providers_config, users
from app.services.storage import DEFAULT_DATA_DIR

router = APIRouter(tags=["providers"])


def get_user_data_dir(request: Request) -> Path:
    """Get the data directory for the current user."""
    session_user = request.cookies.get("aiframe_session")
    if session_user:
        return users.get_user_data_dir(session_user)
    return DEFAULT_DATA_DIR


class UpdateProviderRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[list[str]] = None
    enabled: Optional[bool] = None


class AddCustomProviderRequest(BaseModel):
    provider_id: str
    name: str
    api_key: str
    base_url: str
    api_format: str = "openai"
    models: Optional[list[str]] = None


class UpdateLocalRequest(BaseModel):
    enabled: Optional[bool] = None
    lm_studio_url: Optional[str] = None
    ollama_enabled: Optional[bool] = None
    ollama_url: Optional[str] = None


@router.get("/providers")
async def list_providers(request: Request):
    """List all providers with their configuration status."""
    data_dir = get_user_data_dir(request)
    config = providers_config.load_providers(data_dir)
    
    result = []
    for provider_id, provider in config.providers.items():
        result.append({
            "id": provider_id,
            "name": provider.name,
            "configured": bool(provider.api_key),
            "enabled": provider.enabled,
            "custom": provider.custom,
            "api_format": provider.api_format,
            "base_url": provider.base_url,
            "models": provider.models if provider.api_key and provider.enabled else []
        })
    
    return {
        "providers": result,
        "local": config.local
    }


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str, request: Request):
    """Get a specific provider's configuration (API key masked)."""
    data_dir = get_user_data_dir(request)
    provider = providers_config.get_provider(data_dir, provider_id)
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    return {
        "id": provider_id,
        "name": provider.name,
        "configured": bool(provider.api_key),
        "api_key_preview": f"...{provider.api_key[-4:]}" if provider.api_key and len(provider.api_key) > 4 else None,
        "base_url": provider.base_url,
        "api_format": provider.api_format,
        "enabled": provider.enabled,
        "models": provider.models,
        "custom": provider.custom
    }


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, req: UpdateProviderRequest, request: Request):
    """Update a provider's configuration."""
    data_dir = get_user_data_dir(request)
    
    provider = providers_config.update_provider(
        data_dir,
        provider_id,
        api_key=req.api_key,
        base_url=req.base_url,
        models=req.models,
        enabled=req.enabled
    )
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    return {
        "success": True,
        "id": provider_id,
        "configured": bool(provider.api_key)
    }


@router.post("/providers/custom")
async def add_custom_provider(req: AddCustomProviderRequest, request: Request):
    """Add a new custom provider."""
    data_dir = get_user_data_dir(request)
    
    # Validate provider_id
    if not req.provider_id.isalnum():
        raise HTTPException(status_code=400, detail="Provider ID must be alphanumeric")
    
    # Check if already exists
    existing = providers_config.get_provider(data_dir, req.provider_id)
    if existing:
        raise HTTPException(status_code=400, detail="Provider ID already exists")
    
    provider = providers_config.add_custom_provider(
        data_dir,
        provider_id=req.provider_id,
        name=req.name,
        api_key=req.api_key,
        base_url=req.base_url,
        api_format=req.api_format,
        models=req.models
    )
    
    return {
        "success": True,
        "id": req.provider_id,
        "name": provider.name
    }


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, request: Request):
    """Delete a custom provider."""
    data_dir = get_user_data_dir(request)
    
    success = providers_config.delete_provider(data_dir, provider_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot delete built-in provider or provider not found")
    
    return {"success": True}


@router.put("/providers/local")
async def update_local_settings(req: UpdateLocalRequest, request: Request):
    """Update local LM Studio/Ollama settings."""
    data_dir = get_user_data_dir(request)
    
    local = providers_config.update_local_settings(
        data_dir,
        enabled=req.enabled,
        lm_studio_url=req.lm_studio_url,
        ollama_enabled=req.ollama_enabled,
        ollama_url=req.ollama_url
    )
    
    return {"success": True, "local": local}
