"""Provider configuration and routing."""
import json
from pathlib import Path
from typing import Optional, AsyncGenerator
import httpx

from . import ollama, lm_studio, providers_config


async def chat_with_provider(
    provider: str,
    model: str,
    messages: list[dict],
    settings: dict,
    data_dir: Optional[Path] = None,
    temperature: float = 0.7
) -> AsyncGenerator[str, None]:
    """Route chat request to the appropriate provider."""
    
    # Local providers
    if provider == "ollama":
        url = settings.get("ollama_url", "http://localhost:11434")
        async for chunk in ollama.chat_completion_stream(url, messages, model, temperature):
            yield chunk
        return
    
    if provider == "local":
        url = settings.get("lm_studio_url", "http://localhost:1234")
        async for chunk in lm_studio.chat_completion_stream(url, messages, model, temperature):
            yield chunk
        return
    
    # Cloud providers - get config
    if data_dir is None:
        yield f"Error: No data directory provided for cloud provider {provider}"
        return
    
    config = providers_config.load_providers(data_dir)
    provider_cfg = config.providers.get(provider)
    
    if not provider_cfg:
        yield f"Unknown provider: {provider}"
        return
    
    if not provider_cfg.api_key:
        yield f"API key not configured for {provider_cfg.name}. Please add your API key in Settings."
        return
    
    # Route based on API format
    if provider_cfg.api_format == "openai":
        async for chunk in _openai_chat_stream(provider_cfg, model, messages, temperature):
            yield chunk
    elif provider_cfg.api_format == "anthropic":
        async for chunk in _anthropic_chat_stream(provider_cfg, model, messages, temperature):
            yield chunk
    elif provider_cfg.api_format == "google":
        async for chunk in _google_chat_stream(provider_cfg, model, messages, temperature):
            yield chunk
    else:
        yield f"Unsupported API format: {provider_cfg.api_format}"


async def _openai_chat_stream(
    provider: providers_config.ProviderConfig,
    model: str,
    messages: list[dict],
    temperature: float
) -> AsyncGenerator[str, None]:
    """Stream chat from OpenAI-compatible API."""
    url = f"{provider.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"Error from {provider.name}: {response.status_code} - {error_text.decode()}"
                    return
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue
    except httpx.HTTPError as e:
        yield f"HTTP error with {provider.name}: {str(e)}"
    except Exception as e:
        yield f"Error with {provider.name}: {str(e)}"


async def _anthropic_chat_stream(
    provider: providers_config.ProviderConfig,
    model: str,
    messages: list[dict],
    temperature: float
) -> AsyncGenerator[str, None]:
    """Stream chat from Anthropic API."""
    url = f"{provider.base_url}/v1/messages"
    headers = {
        "x-api-key": provider.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    
    # Convert messages to Anthropic format
    system_message = None
    anthropic_messages = []
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            system_message = content
        else:
            anthropic_messages.append({
                "role": role if role in ["user", "assistant"] else "user",
                "content": content
            })
    
    payload = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": 4096,
        "stream": True
    }
    
    if system_message:
        payload["system"] = system_message
    
    if temperature is not None:
        payload["temperature"] = temperature
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"Error from Anthropic: {response.status_code} - {error_text.decode()}"
                    return
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    data = line[6:]
                    try:
                        chunk = json.loads(data)
                        event_type = chunk.get("type", "")
                        
                        if event_type == "content_block_delta":
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue
    except httpx.HTTPError as e:
        yield f"HTTP error with Anthropic: {str(e)}"
    except Exception as e:
        yield f"Error with Anthropic: {str(e)}"


async def _google_chat_stream(
    provider: providers_config.ProviderConfig,
    model: str,
    messages: list[dict],
    temperature: float
) -> AsyncGenerator[str, None]:
    """Stream chat from Google Generative AI API."""
    url = f"{provider.base_url}/models/{model}:streamGenerateContent?key={provider.api_key}"
    headers = {"Content-Type": "application/json"}
    
    # Convert messages to Google format
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Google uses "user" and "model" roles
        google_role = "model" if role == "assistant" else "user"
        contents.append({
            "role": google_role,
            "parts": [{"text": content}]
        })
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"Error from Google: {response.status_code} - {error_text.decode()}"
                    return
                
                buffer = ""
                async for chunk_bytes in response.aiter_bytes():
                    buffer += chunk_bytes.decode()
                    
                    # Google sends JSON array chunks
                    while True:
                        try:
                            # Try to parse accumulated buffer
                            # Google returns streaming JSON - each line is a complete JSON object
                            lines = buffer.split("\n")
                            for i, line in enumerate(lines[:-1]):  # Process all complete lines
                                line = line.strip()
                                if not line or line == "[" or line == "]" or line == ",":
                                    continue
                                # Remove trailing comma if present
                                if line.endswith(","):
                                    line = line[:-1]
                                try:
                                    data = json.loads(line)
                                    candidates = data.get("candidates", [])
                                    for candidate in candidates:
                                        content = candidate.get("content", {})
                                        parts = content.get("parts", [])
                                        for part in parts:
                                            text = part.get("text", "")
                                            if text:
                                                yield text
                                except json.JSONDecodeError:
                                    pass
                            buffer = lines[-1]  # Keep incomplete line
                            break
                        except:
                            break
    except httpx.HTTPError as e:
        yield f"HTTP error with Google: {str(e)}"
    except Exception as e:
        yield f"Error with Google: {str(e)}"
