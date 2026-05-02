"""LM Studio API client (OpenAI-compatible)."""
import httpx
from typing import AsyncGenerator, Optional
import json


class LMStudioError(Exception):
    """Custom exception for LM Studio errors."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)


async def list_models(url: str) -> list[dict]:
    """Get list of available models from LM Studio."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/v1/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
    except httpx.RequestError as e:
        print(f"[LM Studio] Error connecting: {e}")
        return []
    except httpx.HTTPStatusError as e:
        print(f"[LM Studio] API error: {e}")
        return []


async def chat_completion_stream(
    url: str,
    messages: list[dict],
    model: str,
    temperature: float = 0.7
) -> AsyncGenerator[str, None]:
    """Stream chat completion from LM Studio (OpenAI-compatible API)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature
    }
    
    print(f"[LM Studio] Sending request to {url}/v1/chat/completions")
    print(f"[LM Studio] Model: {model}, Messages: {len(messages)}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_text = error_body.decode('utf-8', errors='replace')
                    print(f"[LM Studio] Error {response.status_code}: {error_text}")
                    raise LMStudioError(
                        "LM Studio returned error",
                        status_code=response.status_code,
                        response_body=error_text
                    )
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            raise LMStudioError(f"Cannot connect to LM Studio at {url}. Is it running?")
        except httpx.RequestError as e:
            raise LMStudioError(f"Request failed: {str(e)}")


async def chat_completion(
    url: str,
    messages: list[dict],
    model: str,
    temperature: float = 0.7
) -> Optional[str]:
    """Non-streaming chat completion from LM Studio."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature
    }
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content")
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"[LM Studio] Error in chat completion: {e}")
        return None
