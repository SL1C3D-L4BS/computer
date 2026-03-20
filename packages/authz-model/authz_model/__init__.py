"""
Authorization Model

v1: RBAC role definitions, relation types, scope grid.
v2 (planned): ReBAC relationship graph types.

Reference: docs/architecture/authorization-evolution.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class UserRole(str, Enum):
    OWNER       = "OWNER"        # Founder/site owner — full access
    ADULT       = "ADULT"        # Adult household member
    TEEN        = "TEEN"         # Teen — personal + household read
    CHILD       = "CHILD"        # Child — household read only; FAMILY mode locked
    GUEST       = "GUEST"        # Guest — household limited read; FAMILY mode locked
    CONTRACTOR  = "CONTRACTOR"   # Scoped to specific work/site resources
    AI_SYSTEM   = "AI_SYSTEM"    # AI advisory — no actuation, no T3+ tools


class ScopeType(str, Enum):
    PERSONAL          = "PERSONAL"
    HOUSEHOLD_SHARED  = "HOUSEHOLD_SHARED"
    WORK              = "WORK"
    SITE              = "SITE"
    GUEST_READ_ONLY   = "GUEST_READ_ONLY"


# Scope access grid (role → allowed scopes for read)
ROLE_READ_SCOPES: dict[UserRole, list[ScopeType]] = {
    UserRole.OWNER:      [ScopeType.PERSONAL, ScopeType.HOUSEHOLD_SHARED, ScopeType.WORK, ScopeType.SITE],
    UserRole.ADULT:      [ScopeType.PERSONAL, ScopeType.HOUSEHOLD_SHARED],
    UserRole.TEEN:       [ScopeType.PERSONAL, ScopeType.HOUSEHOLD_SHARED],
    UserRole.CHILD:      [ScopeType.HOUSEHOLD_SHARED, ScopeType.GUEST_READ_ONLY],
    UserRole.GUEST:      [ScopeType.GUEST_READ_ONLY],
    UserRole.CONTRACTOR: [ScopeType.WORK],  # Further scoped by resource binding
    UserRole.AI_SYSTEM:  [],  # AI has no direct memory access
}


@dataclass
class UserIdentity:
    """v1 RBAC user record."""
    user_id: str
    role: UserRole
    household_id: str
    allowed_scopes: list[ScopeType] = field(default_factory=list)

    def __post_init__(self):
        if not self.allowed_scopes:
            self.allowed_scopes = ROLE_READ_SCOPES.get(self.role, [])
