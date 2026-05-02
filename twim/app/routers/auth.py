"""Authentication endpoints."""
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from app.services import users

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str


class LoginResponse(BaseModel):
    success: bool
    username: str
    display_name: str


@router.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    """Authenticate a user."""
    user = users.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    
    response.set_cookie(
        key="twim_session",
        value=user.username,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
        expires=expires
    )
    
    return LoginResponse(
        success=True,
        username=user.username,
        display_name=user.display_name
    )


@router.post("/auth/logout")
async def logout(response: Response):
    """Log out current user."""
    response.delete_cookie(key="twim_session", path="/")
    return {"success": True}


@router.post("/auth/register")
async def register(request: RegisterRequest, response: Response):
    """Create a new user account."""
    if not request.username or len(request.username) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if not request.username.isalnum():
        raise HTTPException(status_code=400, detail="Username must be alphanumeric")
    if not request.password or len(request.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    
    user = users.create_user(
        username=request.username.lower(),
        password=request.password,
        display_name=request.display_name or request.username
    )
    
    if not user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    response.set_cookie(
        key="twim_session",
        value=user.username,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
        expires=expires
    )
    
    return LoginResponse(
        success=True,
        username=user.username,
        display_name=user.display_name
    )


@router.get("/auth/me")
async def get_current_user(request: Request, response: Response):
    """Get current logged-in user info."""
    session_user = request.cookies.get("twim_session")
    
    if not session_user:
        return {"logged_in": False}
    
    user = users.get_user(session_user)
    if not user:
        return {"logged_in": False}
    
    # Refresh cookie
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    response.set_cookie(
        key="twim_session",
        value=user.username,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
        expires=expires
    )

    return {
        "logged_in": True,
        "username": user.username,
        "display_name": user.display_name
    }


@router.get("/auth/has-users")
async def has_users():
    """Check if any users exist (for first-run setup)."""
    return {"has_users": users.has_users()}


@router.get("/users")
async def list_all_users():
    """List all usernames (for login/switch user)."""
    return {"users": users.list_users()}
