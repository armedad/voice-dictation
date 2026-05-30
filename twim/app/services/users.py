"""User management service."""
import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from .time_utils import utc_now_iso_z

# Users directory
PROJECT_DIR = Path(__file__).parent.parent.parent
_override_users = os.environ.get("TWIM_USERS_DIR")
USERS_DIR = Path(_override_users) if _override_users else PROJECT_DIR / "users"
USERS_FILE = USERS_DIR / "users.json"


class User(BaseModel):
    username: str
    password: str
    display_name: str
    created_at: str


class UsersConfig(BaseModel):
    users: dict[str, User] = {}


def ensure_users_dir():
    """Ensure users directory exists."""
    USERS_DIR.mkdir(parents=True, exist_ok=True)


def get_users_config() -> UsersConfig:
    """Load users configuration."""
    ensure_users_dir()
    if not USERS_FILE.exists():
        config = UsersConfig()
        save_users_config(config)
        return config
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    users = {}
    for username, user_data in data.get("users", {}).items():
        users[username] = User(**user_data)
    return UsersConfig(users=users)


def save_users_config(config: UsersConfig):
    """Save users configuration."""
    ensure_users_dir()
    data = {"users": {}}
    for username, user in config.users.items():
        data["users"][username] = user.model_dump()
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_user(username: str) -> Optional[User]:
    """Get a user by username."""
    config = get_users_config()
    return config.users.get(username)


def create_user(username: str, password: str, display_name: str) -> Optional[User]:
    """Create a new user."""
    config = get_users_config()
    
    if username in config.users:
        return None
    
    user = User(
        username=username,
        password=password,
        display_name=display_name,
        created_at=utc_now_iso_z()
    )
    
    config.users[username] = user
    save_users_config(config)
    
    # Create user's data directory
    user_data_dir = get_user_data_dir(username)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    (user_data_dir / "conversations").mkdir(exist_ok=True)
    
    return user


def update_user(username: str, password: Optional[str] = None, 
                display_name: Optional[str] = None) -> Optional[User]:
    """Update user details."""
    config = get_users_config()
    
    if username not in config.users:
        return None
    
    user = config.users[username]
    if password is not None:
        user.password = password
    if display_name is not None:
        user.display_name = display_name
    
    save_users_config(config)
    return user


def delete_user(username: str) -> bool:
    """Delete a user."""
    config = get_users_config()
    
    if username not in config.users:
        return False
    
    del config.users[username]
    save_users_config(config)
    return True


def authenticate(username: str, password: str) -> Optional[User]:
    """Authenticate a user."""
    user = get_user(username)
    if user and user.password == password:
        return user
    return None


def list_users() -> list[dict]:
    """List all users (without passwords)."""
    config = get_users_config()
    return [
        {
            "username": user.username,
            "display_name": user.display_name,
            "created_at": user.created_at
        }
        for user in config.users.values()
    ]


def get_user_data_dir(username: str) -> Path:
    """Get the data directory for a user."""
    return USERS_DIR / username


def has_users() -> bool:
    """Check if any users exist."""
    config = get_users_config()
    return len(config.users) > 0
