"""Ollama API client."""
import httpx
from typing import AsyncGenerator, Optional
import json


class OllamaError(Exception):
    """Custom exception for Ollama errors."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)


async def list_models(url: str) -> list[dict]:
    """Get list of available models from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
    except httpx.RequestError as e:
        print(f"[Ollama] Error connecting: {e}")
        return []
    except httpx.HTTPStatusError as e:
        print(f"[Ollama] API error: {e}")
        return []


async def chat_completion_stream(
    url: str,
    messages: list[dict],
    model: str,
    temperature: float = 0.7
) -> AsyncGenerator[str, None]:
    """Stream chat completion from Ollama."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }
    
    if temperature != 0.7:
        payload["options"] = {"temperature": temperature}
    
    print(f"[Ollama] Sending request to {url}/api/chat")
    print(f"[Ollama] Model: {model}, Messages: {len(messages)}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_text = error_body.decode('utf-8', errors='replace')
                    print(f"[Ollama] Error {response.status_code}: {error_text}")
                    raise OllamaError(
                        "Ollama returned error",
                        status_code=response.status_code,
                        response_body=error_text
                    )
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    if chunk.get("done"):
                        break
                    
                    message = chunk.get("message") or {}
                    content = message.get("content", "")
                    
                    if content:
                        yield content
        except httpx.ConnectError:
            raise OllamaError(f"Cannot connect to Ollama at {url}. Is it running?")
        except httpx.RequestError as e:
            raise OllamaError(f"Request failed: {str(e)}")


async def chat_completion(
    url: str,
    messages: list[dict],
    model: str,
    temperature: float = 0.7
) -> Optional[str]:
    """Non-streaming chat completion from Ollama."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    
    if temperature != 0.7:
        payload["options"] = {"temperature": temperature}
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{url}/api/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            message = data.get("message") or {}
            return message.get("content")
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"[Ollama] Error in chat completion: {e}")
        return None
