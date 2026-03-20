"""
Context Router Service

The context-router resolves every assistant request into a typed ContextEnvelope
before it reaches the model-router or assistant-api.

Per ADR-016: every voice interaction goes through intent classification
(PERSONAL | HOUSEHOLD | SITE_OPS | HIGH_RISK_CONTROL) before tool execution.

The ContextEnvelope produced here determines:
  - user_id, role (from identity-service)
  - mode (from user preference or explicit switch)
  - intent_class (from keyword/embedding classification)
  - eligible_memory_scopes (from role policy)
  - max_tool_tier (from role + mode)

This service NEVER:
  - Stores memory (memory-service handles this)
  - Executes tools (model-router handles this)
  - Makes policy decisions about jobs (orchestrator handles this)
"""
from __future__ import annotations

import os
import re

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://localhost:8030")


class ResolveRequest(BaseModel):
    user_id: str
    mode: str | None = None  # Override; if None, use user's preferred mode
    message: str  # The user's message for intent classification
    surface: str = "ops-web"  # voice-gateway | family-web | ops-web | cli


class ContextEnvelope(BaseModel):
    user_id: str
    role: str
    mode: str
    eligible_memory_scopes: list[str]
    intent_class: str  # PERSONAL | HOUSEHOLD | SITE_OPS | HIGH_RISK_CONTROL
    max_tool_tier: str
    surface: str
    resolution_trace: list[str] = []


# Intent classification — keyword-based (production: use embedding model)
_SITE_OPS_KEYWORDS = [
    r"\birrigat\b", r"\bgreenhouse\b", r"\bhydro\b", r"\bpump\b",
    r"\bvalve\b", r"\bheater\b", r"\bfan\b", r"\bthermostat\b",
    r"\bbattery\b", r"\bsolar\b", r"\benergy\b", r"\bpanel\b",
    r"\btemperature\b", r"\bhumidity\b", r"\bph\b", r"\bec\b",
    r"\bcamera\b", r"\bsecurity\b", r"\bmotion\b", r"\bincident\b",
    r"\bsensor\b", r"\basset\b",
]

_HIGH_RISK_KEYWORDS = [
    r"\bdrone\b", r"\barm\b", r"\blaunch\b", r"\brover\b",
    r"\bmission\b", r"\be.?stop\b", r"\bemergency\b",
    r"\bshutdown\b", r"\bturn off all\b",
]

_HOUSEHOLD_KEYWORDS = [
    r"\bcalendar\b", r"\bschedule\b", r"\breminder\b", r"\btask\b",
    r"\bshopping\b", r"\bgrocery\b", r"\bchore\b", r"\bmeal\b",
    r"\brecipe\b", r"\bkids?\b", r"\bfamily\b", r"\bhousehold\b",
]


def _classify_intent(message: str) -> str:
    msg_lower = message.lower()

    for pattern in _HIGH_RISK_KEYWORDS:
        if re.search(pattern, msg_lower):
            return "HIGH_RISK_CONTROL"

    for pattern in _SITE_OPS_KEYWORDS:
        if re.search(pattern, msg_lower):
            return "SITE_OPS"

    for pattern in _HOUSEHOLD_KEYWORDS:
        if re.search(pattern, msg_lower):
            return "HOUSEHOLD"

    return "PERSONAL"


def _get_max_tool_tier(role: str, mode: str, intent_class: str) -> str:
    """Derive max tool tier from role × mode × intent."""
    role_tiers = {
        "FOUNDER_ADMIN": "HIGH",
        "ADULT_MEMBER": "LOW",
        "CHILD_GUEST": "INFORMATIONAL",
        "MAINTENANCE_OPERATOR": "MEDIUM",
    }
    base_tier = role_tiers.get(role, "INFORMATIONAL")

    # Reduce tier in FAMILY mode — protect non-technical household members
    if mode in ("FAMILY",) and role != "MAINTENANCE_OPERATOR":
        if base_tier in ("HIGH", "MEDIUM"):
            base_tier = "LOW"

    # Only FOUNDER_ADMIN can use HIGH tier for control operations
    if intent_class == "HIGH_RISK_CONTROL" and role != "FOUNDER_ADMIN":
        return "INFORMATIONAL"

    return base_tier


def _get_memory_scopes_for_role(role: str) -> list[str]:
    scope_map = {
        "FOUNDER_ADMIN": ["PERSONAL", "HOUSEHOLD_SHARED", "SITE_SYSTEM"],
        "ADULT_MEMBER": ["PERSONAL", "HOUSEHOLD_SHARED"],
        "CHILD_GUEST": ["PERSONAL", "HOUSEHOLD_SHARED"],
        "MAINTENANCE_OPERATOR": ["SITE_SYSTEM"],
    }
    return scope_map.get(role, [])


app = FastAPI(
    title="Context Router",
    description="Per-request context resolution and intent classification (ADR-016)",
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
    return {"status": "ok", "service": "context-router", "version": "0.1.0"}


@app.post("/resolve", response_model=ContextEnvelope, tags=["context"])
async def resolve_context(req: ResolveRequest):
    """
    Resolve request context into a ContextEnvelope.
    Called by assistant-api and voice-gateway before every inference request.
    """
    trace = []

    # Get user permissions from identity-service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{IDENTITY_SERVICE_URL}/users/{req.user_id}/permissions")
            if resp.status_code == 404:
                raise HTTPException(status_code=401, detail="User not found")
            if resp.status_code != 200:
                raise HTTPException(status_code=503, detail="Identity service unavailable")
            perms = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        # Fallback for dev: if identity-service unavailable, use dev defaults
        logger.warning("identity_service_unavailable_using_fallback", error=str(e))
        perms = {
            "role": "FOUNDER_ADMIN",
            "max_tool_tier": "HIGH",
            "eligible_memory_scopes": ["PERSONAL", "HOUSEHOLD_SHARED", "SITE_SYSTEM"],
        }
        trace.append("identity_service_fallback")

    role = perms.get("role", "ADULT_MEMBER")

    # Determine mode
    mode = req.mode or "PERSONAL"
    # Validate mode — SITE mode requires FOUNDER_ADMIN or MAINTENANCE_OPERATOR
    if mode == "SITE" and role not in ("FOUNDER_ADMIN", "MAINTENANCE_OPERATOR"):
        mode = "PERSONAL"
        trace.append(f"mode_downgraded: SITE→PERSONAL (role={role})")

    # Classify intent
    intent_class = _classify_intent(req.message)
    trace.append(f"intent_classified: {intent_class}")

    # Derive tool tier
    max_tool_tier = _get_max_tool_tier(role, mode, intent_class)
    trace.append(f"tool_tier: {max_tool_tier}")

    # Memory scopes
    memory_scopes = _get_memory_scopes_for_role(role)

    envelope = ContextEnvelope(
        user_id=req.user_id,
        role=role,
        mode=mode,
        eligible_memory_scopes=memory_scopes,
        intent_class=intent_class,
        max_tool_tier=max_tool_tier,
        surface=req.surface,
        resolution_trace=trace,
    )

    logger.info(
        "context_resolved",
        user_id=req.user_id,
        role=role,
        mode=mode,
        intent_class=intent_class,
        max_tool_tier=max_tool_tier,
    )

    return envelope
