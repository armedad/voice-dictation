"""Provider configuration management."""
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""
    name: str
    api_key: Optional[str] = None
    base_url: str
    api_format: str = "openai"  # openai, anthropic, google
    enabled: bool = True
    models: list[str] = []
    custom: bool = False


class ProvidersConfig(BaseModel):
    """All provider configurations."""
    providers: dict[str, ProviderConfig] = {}
    local: dict = {
        "enabled": True,
        "lm_studio_url": "http://localhost:1234",
        "ollama_enabled": True,
        "ollama_url": "http://localhost:11434"
    }


# Built-in provider defaults
BUILTIN_PROVIDERS = {
    "openai": ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_format="openai",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo"
        ]
    ),
    "anthropic": ProviderConfig(
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_format="anthropic",
        models=[
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307"
        ]
    ),
    "google": ProviderConfig(
        name="Google",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_format="google",
        models=["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
    ),
    "groq": ProviderConfig(
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_format="openai",
        models=["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
    )
}


def get_providers_file(data_dir: Path) -> Path:
    """Get the providers.json path for a data directory."""
    return data_dir / "providers.json"


def load_providers(data_dir: Path) -> ProvidersConfig:
    """Load providers configuration."""
    providers_file = get_providers_file(data_dir)
    
    if not providers_file.exists():
        # Initialize with built-in providers (no API keys)
        config = ProvidersConfig()
        for provider_id, provider in BUILTIN_PROVIDERS.items():
            config.providers[provider_id] = provider.model_copy()
        save_providers(data_dir, config)
        return config
    
    with open(providers_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Parse providers
    providers = {}
    for provider_id, provider_data in data.get("providers", {}).items():
        providers[provider_id] = ProviderConfig(**provider_data)
    
    # Ensure all built-in providers exist
    for provider_id, default_provider in BUILTIN_PROVIDERS.items():
        if provider_id not in providers:
            providers[provider_id] = default_provider.model_copy()
    
    default_local = {
        "enabled": True,
        "lm_studio_url": "http://localhost:1234",
        "ollama_enabled": True,
        "ollama_url": "http://localhost:11434"
    }
    
    local = data.get("local") or {}
    merged_local = {**default_local, **local}
    
    return ProvidersConfig(
        providers=providers,
        local=merged_local
    )


def save_providers(data_dir: Path, config: ProvidersConfig):
    """Save providers configuration."""
    data_dir.mkdir(parents=True, exist_ok=True)
    providers_file = get_providers_file(data_dir)
    
    data = {
        "providers": {},
        "local": config.local
    }
    for provider_id, provider in config.providers.items():
        data["providers"][provider_id] = provider.model_dump()
    
    with open(providers_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_provider(data_dir: Path, provider_id: str) -> Optional[ProviderConfig]:
    """Get a specific provider config."""
    config = load_providers(data_dir)
    return config.providers.get(provider_id)


def update_provider(data_dir: Path, provider_id: str, api_key: Optional[str] = None,
                   base_url: Optional[str] = None, models: Optional[list[str]] = None,
                   enabled: Optional[bool] = None) -> Optional[ProviderConfig]:
    """Update a provider configuration."""
    config = load_providers(data_dir)
    
    if provider_id not in config.providers:
        return None
    
    provider = config.providers[provider_id]
    if api_key is not None:
        provider.api_key = api_key if api_key else None
    if base_url is not None:
        provider.base_url = base_url
    if models is not None:
        provider.models = models
    if enabled is not None:
        provider.enabled = enabled
    
    save_providers(data_dir, config)
    return provider


def add_custom_provider(data_dir: Path, provider_id: str, name: str, api_key: str,
                       base_url: str, api_format: str = "openai",
                       models: Optional[list[str]] = None) -> ProviderConfig:
    """Add a custom provider."""
    config = load_providers(data_dir)
    
    provider = ProviderConfig(
        name=name,
        api_key=api_key,
        base_url=base_url,
        api_format=api_format,
        enabled=True,
        models=models or [],
        custom=True
    )
    
    config.providers[provider_id] = provider
    save_providers(data_dir, config)
    return provider


def delete_provider(data_dir: Path, provider_id: str) -> bool:
    """Delete a custom provider."""
    config = load_providers(data_dir)
    
    if provider_id not in config.providers:
        return False
    
    # Only allow deleting custom providers
    if not config.providers[provider_id].custom:
        return False
    
    del config.providers[provider_id]
    save_providers(data_dir, config)
    return True


def get_configured_providers(data_dir: Path) -> list[dict]:
    """Get list of providers with their configuration status."""
    config = load_providers(data_dir)
    
    result = []
    for provider_id, provider in config.providers.items():
        result.append({
            "id": provider_id,
            "name": provider.name,
            "configured": bool(provider.api_key),
            "enabled": provider.enabled,
            "models": provider.models if provider.api_key else [],
            "custom": provider.custom,
            "api_format": provider.api_format
        })
    
    return result


def update_local_settings(data_dir: Path, enabled: Optional[bool] = None,
                         lm_studio_url: Optional[str] = None,
                         ollama_enabled: Optional[bool] = None,
                         ollama_url: Optional[str] = None):
    """Update local LM Studio/Ollama settings."""
    config = load_providers(data_dir)
    
    if enabled is not None:
        config.local["enabled"] = enabled
    if lm_studio_url is not None:
        config.local["lm_studio_url"] = lm_studio_url
    if ollama_enabled is not None:
        config.local["ollama_enabled"] = ollama_enabled
    if ollama_url is not None:
        config.local["ollama_url"] = ollama_url
    
    save_providers(data_dir, config)
    return config.local
