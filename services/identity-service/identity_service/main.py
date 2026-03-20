"""
Identity Service

Responsibilities:
  - Manage household user accounts and roles (ADR-012)
  - Issue JWT tokens
  - Validate tokens for other services
  - Provide permission checks

This is the authoritative source for user identity and roles.
All services check roles via this service or the JWT claim.
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import (
    AssistantMode,
    HouseholdRole,
    LoginRequest,
    TokenResponse,
    User,
    get_eligible_memory_scopes,
    get_max_tool_tier,
    has_permission,
)

logger = structlog.get_logger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 86400  # 24 hours

# In-memory user store for development
# Production: Postgres-backed
_users: dict[str, User] = {
    "founder": User(
        user_id="user-founder-001",
        name="Founder",
        role=HouseholdRole.FOUNDER_ADMIN,
        email="founder@computer.local",
        created_at=datetime.utcnow(),
    ),
    "dev": User(
        user_id="user-dev-001",
        name="Dev User",
        role=HouseholdRole.FOUNDER_ADMIN,
        email="dev@computer.local",
        created_at=datetime.utcnow(),
    ),
}

# Simple password store (production: use bcrypt hashes in DB)
_passwords: dict[str, str] = {
    "founder": hashlib.sha256(b"founder-password").hexdigest(),
    "dev": hashlib.sha256(b"dev-password").hexdigest(),
}


def _create_jwt(user: User) -> str:
    """Create a JWT token for a user."""
    try:
        from jose import jwt
        payload = {
            "sub": user.user_id,
            "role": user.role.value,
            "name": user.name,
            "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    except ImportError:
        # Fallback for dev without jose
        import base64, json
        payload = {"sub": user.user_id, "role": user.role.value, "name": user.name}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        return f"dev-token.{encoded}.signature"


def _verify_jwt(token: str) -> dict | None:
    """Verify and decode a JWT token."""
    try:
        from jose import jwt, JWTError
        try:
            return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            return None
    except ImportError:
        # Dev fallback
        if token.startswith("dev-token.") or token == "dev-token":
            return {"sub": "user-founder-001", "role": "FOUNDER_ADMIN", "name": "Dev"}
        return None


app = FastAPI(
    title="Identity Service",
    description="Household identity, roles, and JWT auth (ADR-012)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "identity-service", "version": "0.1.0", "users": len(_users)}


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(req: LoginRequest):
    """Authenticate a user and return a JWT token."""
    password_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if req.username not in _users or _passwords.get(req.username) != password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = _users[req.username]
    token = _create_jwt(user)
    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        role=user.role,
        name=user.name,
    )


@app.post("/auth/verify", tags=["auth"])
async def verify_token(token: str):
    """Verify a JWT token and return claims."""
    claims = _verify_jwt(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims


@app.get("/users/{user_id}", tags=["users"])
async def get_user(user_id: str):
    """Get user by ID."""
    for user in _users.values():
        if user.user_id == user_id:
            return user.model_dump(exclude={"metadata"})
    raise HTTPException(status_code=404, detail="User not found")


@app.get("/users/{user_id}/permissions", tags=["users"])
async def get_user_permissions(user_id: str):
    """Get resolved permissions for a user."""
    user = None
    for u in _users.values():
        if u.user_id == user_id:
            user = u
            break
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_id,
        "role": user.role,
        "max_tool_tier": get_max_tool_tier(user.role),
        "eligible_memory_scopes": get_eligible_memory_scopes(user.role),
        "permissions": {
            "site:e_stop": has_permission(user.role, "site:e_stop"),
            "ai:high_risk_tools": has_permission(user.role, "ai:high_risk_tools"),
            "family:manage_members": has_permission(user.role, "family:manage_members"),
        },
    }


class CreateUserRequest(BaseModel):
    username: str
    password: str
    name: str
    role: HouseholdRole
    email: str | None = None


@app.post("/users", response_model=User, status_code=201, tags=["users"])
async def create_user(req: CreateUserRequest):
    """Create a new household user (FOUNDER_ADMIN only in production)."""
    if req.username in _users:
        raise HTTPException(status_code=409, detail="Username already exists")
    import uuid
    user = User(
        user_id=str(uuid.uuid4()),
        name=req.name,
        role=req.role,
        email=req.email,
        created_at=datetime.utcnow(),
    )
    _users[req.username] = user
    _passwords[req.username] = hashlib.sha256(req.password.encode()).hexdigest()
    logger.info("user_created", user_id=user.user_id, role=req.role)
    return user
