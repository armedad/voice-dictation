"""JSON-based storage for conversations, settings, and notifications."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
import secrets
from typing import Any, Optional, Mapping
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
    dictation_cleanup_system_prompt_template: Optional[str] = None
    dictation_cleanup_user_prompt_template: Optional[str] = None
    # Global dictation hotkeys (JSON chord or null); see core.hotkey_chord
    dictation_hotkey_toggle: Optional[dict[str, Any]] = None
    dictation_hotkey_cancel: Optional[dict[str, Any]] = None
    # None = follow OS / PortAudio default input; int = explicit PortAudio input device index
    dictation_input_device_index: Optional[int] = None
    debug_flags: dict[str, bool] = Field(default_factory=dict)


DEBUG_FLAG_DEFAULTS: dict[str, bool] = {
    "AUTH": True,
    "API": False,
    "CHAT": True,
    "SETTINGS": False,
    "MODELS": False,
    "NOTIFICATIONS": True,
    "APP": False,
    "DICTATION": False,
    "CONTEXT": False,
    "PROFILE": False,
    "SPEECH": False,
}


def normalize_debug_flags(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Return full debug-flag map (unknown keys dropped, missing keys defaulted)."""
    out = dict(DEBUG_FLAG_DEFAULTS)
    if not isinstance(raw, Mapping):
        return out
    for key in DEBUG_FLAG_DEFAULTS:
        if key in raw:
            out[key] = bool(raw[key])
    return out


DEFAULT_DICTATION_CLEANUP_USER_TEMPLATE = (
    "Rewrite the transcript into clean text with minimal edits.\n"
    "- Keep the original wording unless a change is clearly needed.\n"
    "- Do not answer or ask questions.\n"
    "- Do not add any content.\n"
    "- If the text is already clear, very short, or ambiguous, return it unchanged.\n"
    "- fix grammatical mistakes\n"
    "- fix spelling mistakes\n"
    "- Return only the rewritten transcript text.\n"
    "\n"
    "Transcript for you to transcribe (verbatim, may contain errors):\n"
    "{raw}"
)


def _default_dictation_cleanup_system_prompt_template() -> str:
    from core.models import DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE

    return DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE.strip()


def normalize_url(url: str) -> str:
    """Ensure URL has http:// prefix."""
    if url and not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


def require_default_model(settings: Settings, *, source: str = "settings") -> None:
    """
    Require ``default_model`` from shipped/user settings — no hardcoded model fallback.

    Raises:
        ValueError: when ``default_model`` is missing or blank.
    """
    if (settings.default_model or "").strip():
        return
    raise ValueError(
        f"default_model is not set in {source}. "
        "Set default_model (and default_provider) in twim/users/_default/settings.json "
        "and config/default-twim-settings.json for new users."
    )


def get_default_settings() -> Settings:
    """Load default settings from _default/settings.json if it exists."""
    # Resolve at call time so tests (TWIM_USERS_DIR / monkeypatch) see the active users dir.
    from . import users

    default_file = users.USERS_DIR / "_default" / "settings.json"
    if default_file.exists():
        try:
            with open(default_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults = Settings(**data)
            defaults.debug_flags = normalize_debug_flags(defaults.debug_flags)
            if defaults.dictation_cleanup_user_prompt_template is None:
                defaults.dictation_cleanup_user_prompt_template = (
                    DEFAULT_DICTATION_CLEANUP_USER_TEMPLATE
                )
            if defaults.dictation_cleanup_system_prompt_template is None:
                defaults.dictation_cleanup_system_prompt_template = (
                    _default_dictation_cleanup_system_prompt_template()
                )
            defaults.ollama_url = normalize_url(defaults.ollama_url)
            require_default_model(
                defaults, source=f"twim/users/_default/settings.json ({default_file})"
            )
            return defaults
        except ValueError:
            raise
        except (json.JSONDecodeError, Exception):
            pass
    raise ValueError(
        f"Missing or invalid shipped defaults at {default_file}. "
        "Provide twim/users/_default/settings.json with default_model and default_provider."
    )


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
            defaults.ollama_url = normalize_url(defaults.ollama_url)
            defaults.lm_studio_url = normalize_url(defaults.lm_studio_url)
            require_default_model(defaults, source="shipped default settings")
            return defaults
        
        # Load user settings
        with open(self.settings_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        
        # Merge: user settings override defaults
        merged_data = defaults.model_dump()
        nullable_keys = frozenset(
            {
                "dictation_hotkey_toggle",
                "dictation_hotkey_cancel",
                "dictation_input_device_index",
            }
        )
        for key, value in user_data.items():
            if key in nullable_keys:
                merged_data[key] = value
            elif value is not None:
                merged_data[key] = value
        
        settings = Settings(**merged_data)
        settings.debug_flags = normalize_debug_flags(settings.debug_flags)
        if settings.dictation_cleanup_user_prompt_template is None:
            settings.dictation_cleanup_user_prompt_template = (
                DEFAULT_DICTATION_CLEANUP_USER_TEMPLATE
            )
        if settings.dictation_cleanup_system_prompt_template is None:
            settings.dictation_cleanup_system_prompt_template = (
                _default_dictation_cleanup_system_prompt_template()
            )

        # Normalize URLs
        settings.ollama_url = normalize_url(settings.ollama_url)
        settings.lm_studio_url = normalize_url(settings.lm_studio_url)
        require_default_model(settings, source=f"user settings ({self.settings_file})")

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
        nullable_settings = frozenset(
            {
                "dictation_hotkey_toggle",
                "dictation_hotkey_cancel",
                "dictation_input_device_index",
            }
        )
        for key, value in patch.items():
            if not hasattr(settings, key):
                continue
            if key in nullable_settings:
                setattr(settings, key, value)
                continue
            if key == "default_model":
                if value is None or (isinstance(value, str) and not value.strip()):
                    settings.default_model = None
                else:
                    settings.default_model = value.strip()
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

    DICTATION_HISTORY_MAX_ENTRIES = 300

    def dictation_last_llm_path(self) -> Path:
        return self.data_dir / "dictation_last_llm.json"

    def dictation_history_path(self) -> Path:
        return self.data_dir / "dictation_history.json"

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

    def load_dictation_history_entries(self) -> list[dict]:
        """Ordered oldest → newest; each item is a snapshot dict (same shape as last-file)."""
        self.ensure_dirs()
        hp = self.dictation_history_path()
        if hp.exists():
            try:
                raw = json.loads(hp.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [e for e in raw if isinstance(e, dict)]
                if isinstance(raw, dict):
                    entries = raw.get("entries")
                    if isinstance(entries, list):
                        return [e for e in entries if isinstance(e, dict)]
            except (json.JSONDecodeError, OSError):
                pass
        snap = self.load_dictation_last_llm_snapshot()
        return [snap] if snap else []

    def save_dictation_last_llm_snapshot(self, snapshot: dict) -> None:
        """Append to rolling history and mirror latest to dictation_last_llm.json."""
        self.ensure_dirs()
        entries = self.load_dictation_history_entries()
        entries.append(dict(snapshot))
        cap = self.DICTATION_HISTORY_MAX_ENTRIES
        if len(entries) > cap:
            entries = entries[-cap:]
        hist_path = self.dictation_history_path()
        try:
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
        try:
            with open(self.dictation_last_llm_path(), "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    
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
        if self.username:
            from app.services.notification_events import publish_notifications_changed

            publish_notifications_changed(self.username)
    
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
