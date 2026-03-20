"""
Identity and role models (ADR-012).

Roles:
  FOUNDER_ADMIN — Full access, e-stop, all system controls
  ADULT_MEMBER — Household access, site read, limited control
  CHILD_GUEST — Household assistant only, no site controls
  MAINTENANCE_OPERATOR — Site control only, no personal memory

See docs/product/household-roles-and-permissions.md for full permission matrix.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class HouseholdRole(str, Enum):
    FOUNDER_ADMIN = "FOUNDER_ADMIN"
    ADULT_MEMBER = "ADULT_MEMBER"
    CHILD_GUEST = "CHILD_GUEST"
    MAINTENANCE_OPERATOR = "MAINTENANCE_OPERATOR"


class AssistantMode(str, Enum):
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"
    WORK = "WORK"
    SITE = "SITE"
    EMERGENCY = "EMERGENCY"


class User(BaseModel):
    user_id: str
    name: str
    role: HouseholdRole
    email: str | None = None
    preferred_mode: AssistantMode = AssistantMode.PERSONAL
    created_at: datetime | None = None
    last_active: datetime | None = None
    is_active: bool = True
    metadata: dict[str, Any] = {}


class TokenPayload(BaseModel):
    sub: str  # user_id
    role: HouseholdRole
    name: str
    exp: int


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: HouseholdRole
    name: str


# Role permissions matrix (condensed)
ROLE_PERMISSIONS: dict[HouseholdRole, dict[str, bool]] = {
    HouseholdRole.FOUNDER_ADMIN: {
        "site:control:all": True,
        "site:read:all": True,
        "site:e_stop": True,
        "assistant:all_modes": True,
        "memory:personal": True,
        "memory:household_shared": True,
        "memory:site_system": True,
        "family:manage_members": True,
        "ai:high_risk_tools": True,
    },
    HouseholdRole.ADULT_MEMBER: {
        "site:control:all": False,
        "site:read:all": True,
        "site:e_stop": False,
        "assistant:all_modes": False,
        "memory:personal": True,
        "memory:household_shared": True,
        "memory:site_system": False,
        "family:manage_members": False,
        "ai:high_risk_tools": False,
    },
    HouseholdRole.CHILD_GUEST: {
        "site:control:all": False,
        "site:read:all": False,
        "site:e_stop": False,
        "assistant:all_modes": False,
        "memory:personal": True,
        "memory:household_shared": True,
        "memory:site_system": False,
        "family:manage_members": False,
        "ai:high_risk_tools": False,
    },
    HouseholdRole.MAINTENANCE_OPERATOR: {
        "site:control:all": True,
        "site:read:all": True,
        "site:e_stop": True,
        "assistant:all_modes": False,
        "memory:personal": False,
        "memory:household_shared": False,
        "memory:site_system": True,
        "family:manage_members": False,
        "ai:high_risk_tools": False,
    },
}


def has_permission(role: HouseholdRole, permission: str) -> bool:
    return ROLE_PERMISSIONS.get(role, {}).get(permission, False)


def get_max_tool_tier(role: HouseholdRole) -> str:
    if role == HouseholdRole.FOUNDER_ADMIN:
        return "HIGH"
    if role == HouseholdRole.MAINTENANCE_OPERATOR:
        return "MEDIUM"
    if role == HouseholdRole.ADULT_MEMBER:
        return "LOW"
    return "INFORMATIONAL"  # CHILD_GUEST


def get_eligible_memory_scopes(role: HouseholdRole) -> list[str]:
    scopes = []
    perms = ROLE_PERMISSIONS.get(role, {})
    if perms.get("memory:personal"):
        scopes.append("PERSONAL")
    if perms.get("memory:household_shared"):
        scopes.append("HOUSEHOLD_SHARED")
    if perms.get("memory:site_system"):
        scopes.append("SITE_SYSTEM")
    return scopes
