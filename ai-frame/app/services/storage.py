"""JSON-based storage for conversations, settings, and notifications."""
import json
from pathlib import Path
from datetime import datetime
import secrets
from typing import Any, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from .users import USERS_DIR


class Message(BaseModel):
    role: str
    content: str
    model: Optional[str] = None
    provider: Optional[str] = None
    timestamp: str


class Conversation(BaseModel):
    id: str
    title: str
    owner: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: str
    updated_at: str
    messages: list[Message] = []


class Settings(BaseModel):
    theme: str = "dark"
    lm_studio_url: str = "http://localhost:1234"
    ollama_url: str = "http://localhost:11434"
    default_model: Optional[str] = None
    default_provider: Optional[str] = "ollama"
    # STT for dictation: "provider:model" (e.g. faster_whisper:small); bare id => faster_whisper:id
    speech_model: Optional[str] = None
    dictation_llm_cleanup_enabled: bool = True
    dictation_instructions: Optional[str] = None
    # Newline-separated preferred terms (proper nouns, acronyms, product names)
    dictation_vocabulary: Optional[str] = None
    dictation_use_default_system_prompt: bool = True
    dictation_custom_system_prompt_base: Optional[str] = None
    # Global dictation hotkeys (JSON chord or null); see core.hotkey_chord
    dictation_hotkey_toggle: Optional[dict[str, Any]] = None
    dictation_hotkey_cancel: Optional[dict[str, Any]] = None


def normalize_url(url: str) -> str:
    """Ensure URL has http:// prefix."""
    if url and not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


def get_default_settings() -> Settings:
    """Load default settings from _default/settings.json if it exists."""
    default_file = USERS_DIR / "_default" / "settings.json"
    if default_file.exists():
        try:
            with open(default_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Settings(**data)
        except (json.JSONDecodeError, Exception):
            pass
    return Settings()


class Notification(BaseModel):
    """User-facing notifications."""
    id: str
    type: str
    message: str
    source: Optional[str] = None
    details: Optional[str] = None
    created_at: str
    dismissed: bool = False


class UserDataStore:
    """Storage operations scoped to a user's data directory."""
    
    def __init__(self, data_dir: Path, username: Optional[str] = None):
        self.data_dir = Path(data_dir)
        self.username = username
        self.conversations_dir = self.data_dir / "conversations"
        self.settings_file = self.data_dir / "settings.json"
        self.providers_file = self.data_dir / "providers.json"
        self.notifications_file = self.data_dir / "notifications.json"
    
    def ensure_dirs(self):
        """Ensure data directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(exist_ok=True)
    
    def get_conversation_path(self, conversation_id: str) -> Path:
        return self.conversations_dir / f"{conversation_id}.json"
    
    # --- Conversations ---
    
    def list_conversations(self) -> list[dict]:
        """List all conversations (metadata only)."""
        self.ensure_dirs()
        conversations = []
        
        for file in self.conversations_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conversations.append({
                        "id": data["id"],
                        "title": data["title"],
                        "provider": data.get("provider"),
                        "model": data.get("model"),
                        "created_at": data["created_at"],
                        "updated_at": data["updated_at"],
                        "message_count": len(data.get("messages", []))
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        
        conversations.sort(key=lambda x: x["updated_at"], reverse=True)
        return conversations
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        path = self.get_conversation_path(conversation_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Conversation(**data)
    
    def create_conversation(self, title: str = "New Chat", provider: Optional[str] = None,
                           model: Optional[str] = None) -> Conversation:
        """Create a new conversation."""
        self.ensure_dirs()
        now = datetime.utcnow().isoformat() + "Z"
        conversation = Conversation(
            id=str(uuid4()),
            title=title,
            owner=self.username,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
            messages=[]
        )
        self.save_conversation(conversation)
        return conversation
    
    def save_conversation(self, conversation: Conversation):
        """Save a conversation to disk."""
        self.ensure_dirs()
        path = self.get_conversation_path(conversation.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conversation.model_dump(), f, indent=2, ensure_ascii=False)
    
    def update_conversation(self, conversation_id: str, title: Optional[str] = None,
                           provider: Optional[str] = None, 
                           model: Optional[str] = None) -> Optional[Conversation]:
        """Update conversation metadata."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        if title is not None:
            conversation.title = title
        if provider is not None:
            conversation.provider = provider
        if model is not None:
            conversation.model = model
        conversation.updated_at = datetime.utcnow().isoformat() + "Z"
        self.save_conversation(conversation)
        return conversation
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        path = self.get_conversation_path(conversation_id)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def add_message(self, conversation_id: str, role: str, content: str,
                   model: Optional[str] = None, 
                   provider: Optional[str] = None) -> Optional[Message]:
        """Add a message to a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        
        message = Message(
            role=role,
            content=content,
            model=model,
            provider=provider,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
        conversation.messages.append(message)
        conversation.updated_at = message.timestamp
        self.save_conversation(conversation)
        return message
    
    # --- Settings ---
    
    def get_settings(self) -> Settings:
        """Get user settings, merging with defaults."""
        self.ensure_dirs()
        
        # Start with system defaults
        defaults = get_default_settings()
        
        if not self.settings_file.exists():
            # No user settings - use defaults
            return defaults
        
        # Load user settings
        with open(self.settings_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        
        # Merge: user settings override defaults
        merged_data = defaults.model_dump()
        nullable_keys = frozenset({"dictation_hotkey_toggle", "dictation_hotkey_cancel"})
        for key, value in user_data.items():
            if key in nullable_keys:
                merged_data[key] = value
            elif value is not None:
                merged_data[key] = value
        
        settings = Settings(**merged_data)
        
        # Normalize URLs
        settings.ollama_url = normalize_url(settings.ollama_url)
        settings.lm_studio_url = normalize_url(settings.lm_studio_url)
        
        return settings
    
    def save_settings(self, settings: Settings):
        """Save settings to disk."""
        self.ensure_dirs()
        # Normalize URLs before saving
        settings.ollama_url = normalize_url(settings.ollama_url)
        settings.lm_studio_url = normalize_url(settings.lm_studio_url)
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(settings.model_dump(), f, indent=2, ensure_ascii=False)
    
    def update_settings(self, **kwargs) -> Settings:
        """Update settings (legacy keyword API; prefer ``update_settings_patch``)."""
        return self.update_settings_patch(dict(kwargs))

    def update_settings_patch(self, patch: dict[str, Any]) -> Settings:
        """Apply only keys present in ``patch``; allows None for nullable hotkey fields."""
        settings = self.get_settings()
        nullable_hotkeys = frozenset({"dictation_hotkey_toggle", "dictation_hotkey_cancel"})
        for key, value in patch.items():
            if not hasattr(settings, key):
                continue
            if key in nullable_hotkeys:
                setattr(settings, key, value)
                continue
            if value is None:
                continue
            if key in ("ollama_url", "lm_studio_url"):
                value = normalize_url(value)
            setattr(settings, key, value)
        self.save_settings(settings)
        return settings

    def hotkey_secret_path(self) -> Path:
        return self.data_dir / "hotkey_local_secret.txt"

    def read_hotkey_secret(self) -> Optional[str]:
        """Return stored secret hex string, or None if missing."""
        path = self.hotkey_secret_path()
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return raw or None

    def ensure_hotkey_secret(self) -> str:
        """Create ``hotkey_local_secret.txt`` if missing; return current secret."""
        self.ensure_dirs()
        path = self.hotkey_secret_path()
        if path.exists():
            existing = self.read_hotkey_secret()
            if existing:
                return existing
        token = secrets.token_hex(32)
        path.write_text(token + "\n", encoding="utf-8")
        return token

    def dictation_last_llm_path(self) -> Path:
        return self.data_dir / "dictation_last_llm.json"

    def save_dictation_last_llm_snapshot(self, snapshot: dict) -> None:
        """Persist last dictation LLM request/response for the Context tab."""
        self.ensure_dirs()
        with open(self.dictation_last_llm_path(), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

    def load_dictation_last_llm_snapshot(self) -> dict:
        """Load last dictation LLM snapshot, or {} if missing/unreadable."""
        self.ensure_dirs()
        path = self.dictation_last_llm_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    
    # --- Notifications ---
    
    def get_notifications(self) -> list[Notification]:
        """Get all notifications for the user."""
        self.ensure_dirs()
        if not self.notifications_file.exists():
            return []
        with open(self.notifications_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [Notification(**n) for n in data]
    
    def save_notifications(self, notifications: list[Notification]):
        """Save notifications to disk."""
        self.ensure_dirs()
        with open(self.notifications_file, "w", encoding="utf-8") as f:
            json.dump([n.model_dump() for n in notifications], f, indent=2)
    
    def add_notification(self, notif_type: str, message: str, 
                        source: Optional[str] = None, 
                        details: Optional[str] = None) -> Notification:
        """Add a notification and return it."""
        notifications = self.get_notifications()
        now = datetime.utcnow().isoformat() + "Z"
        notif = Notification(
            id=str(uuid4()),
            type=notif_type,
            message=message,
            source=source,
            details=details,
            created_at=now,
            dismissed=False
        )
        notifications.insert(0, notif)
        self.save_notifications(notifications)
        return notif
    
    def dismiss_notification(self, notif_id: str) -> bool:
        """Mark a notification as dismissed."""
        notifications = self.get_notifications()
        updated = False
        for n in notifications:
            if n.id == notif_id:
                n.dismissed = True
                updated = True
                break
        if updated:
            self.save_notifications(notifications)
        return updated
    
    def dismiss_all_notifications(self) -> int:
        """Mark all notifications as dismissed."""
        notifications = self.get_notifications()
        count = 0
        for n in notifications:
            if not n.dismissed:
                n.dismissed = True
                count += 1
        if count > 0:
            self.save_notifications(notifications)
        return count
    
    def delete_notification(self, notif_id: str) -> bool:
        """Delete a notification permanently."""
        notifications = self.get_notifications()
        original_count = len(notifications)
        notifications = [n for n in notifications if n.id != notif_id]
        if len(notifications) < original_count:
            self.save_notifications(notifications)
            return True
        return False
    
    def delete_all_notifications(self) -> int:
        """Delete all notifications permanently."""
        notifications = self.get_notifications()
        count = len(notifications)
        if count > 0:
            self.save_notifications([])
        return count


# Default data directory for unauthenticated requests
DEFAULT_DATA_DIR = USERS_DIR / "_default"
