"""Chat endpoints with streaming support."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from typing import Optional
from pathlib import Path
import json

from app.services import users
from app.services.storage import UserDataStore, DEFAULT_DATA_DIR
from app.services.providers import chat_with_provider

router = APIRouter(tags=["chat"])


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


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None


class ConversationRequest(BaseModel):
    title: Optional[str] = "New Chat"
    provider: Optional[str] = None
    model: Optional[str] = None


@router.get("/conversations")
async def list_conversations(request: Request):
    """List all conversations."""
    store = get_user_store(request)
    conversations = store.list_conversations()
    return {"conversations": conversations}


@router.post("/conversations")
async def create_conversation(request: Request, req: ConversationRequest):
    """Create a new conversation."""
    store = get_user_store(request)
    conversation = store.create_conversation(
        title=req.title,
        provider=req.provider,
        model=req.model
    )
    return conversation.model_dump()


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request):
    """Get a conversation by ID."""
    store = get_user_store(request)
    conversation = store.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.model_dump()


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    """Delete a conversation."""
    store = get_user_store(request)
    success = store.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@router.post("/chat")
async def chat(request: Request, req: ChatRequest):
    """Send a chat message and get streaming response."""
    store = get_user_store(request)
    data_dir = get_user_data_dir(request)
    settings = store.get_settings()
    
    # Get or create conversation
    if req.conversation_id:
        conversation = store.get_conversation(req.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = store.create_conversation(
            title="New Chat",
            provider=req.provider or settings.default_provider,
            model=req.model or settings.default_model
        )
    
    # Determine provider and model
    provider = req.provider or conversation.provider or settings.default_provider or "ollama"
    model = req.model or conversation.model or settings.default_model
    
    if not model:
        raise HTTPException(status_code=400, detail="No model specified")
    
    # Add user message
    store.add_message(conversation.id, "user", req.message)
    
    # Build messages for LLM
    conversation = store.get_conversation(conversation.id)
    llm_messages = [
        {"role": m.role, "content": m.content}
        for m in conversation.messages
    ]
    
    async def generate():
        full_response = ""
        try:
            async for chunk in chat_with_provider(
                provider=provider,
                model=model,
                messages=llm_messages,
                settings=settings.model_dump(),
                data_dir=data_dir
            ):
                full_response += chunk
                yield {"event": "message", "data": json.dumps({"content": chunk})}
            
            # Save assistant response
            store.add_message(
                conversation.id, 
                "assistant", 
                full_response,
                model=model,
                provider=provider
            )
            
            yield {"event": "done", "data": json.dumps({
                "conversation_id": conversation.id,
                "model": model,
                "provider": provider
            })}
            
        except Exception as e:
            print(f"[Chat] Error: {e}")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
    
    return EventSourceResponse(generate())
