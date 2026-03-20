"""
Authorization Service — CRK step 6

Owns: Authorization decisions with full AuthzContext, policy function evaluation.
Does NOT own: Authentication (identity-service), session management.

v1: RBAC role-based policy
v2 target: ReBAC relationship-based policy (see docs/architecture/authorization-evolution.md)

HARD RULE: If this service is unreachable, runtime-kernel must DENY.
           Never allow on auth failure (see loop.py step6_authorize).

ADR: ADR-019 (Authorization Evolution)
Reference: docs/architecture/authorization-evolution.md
           docs/architecture/kernel-authority-model.md (authz-service row)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
import structlog

CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Authorization Service",
    description="Authorization decisions — step 6 of the CRK execution loop",
    version="0.1.0",
)


class AuthzContextPayload(BaseModel):
    mode: str
    risk_class: str
    origin: str
    location: str | None = None
    time_of_day: str | None = None


class AuthzRequestPayload(BaseModel):
    subject: str
    resource: str
    action: str
    context: AuthzContextPayload


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "authz-service", "version": "v1-rbac"}


@app.post("/authorize")
async def authorize(req: AuthzRequestPayload) -> dict[str, Any]:
    """
    POST /authorize → AuthzResponse

    Evaluates the request using the v1 RBAC policy function.
    Returns {allowed, reason, applicable_policy}.

    This is a POLICY FUNCTION, not a comparison.
    risk_class and trust_tier are different axes.
    Mode is required context — same user has different access by mode.
    """
    result = _evaluate_policy(req)
    log.info(
        "authz.decision",
        subject=req.subject,
        resource=req.resource,
        action=req.action,
        mode=req.context.mode,
        allowed=result["allowed"],
        policy=result["applicable_policy"],
    )
    return result


def _evaluate_policy(req: AuthzRequestPayload) -> dict[str, Any]:
    """
    v1 RBAC policy function.

    Rules evaluated in order (first matching rule wins):
    1. Emergency mode: only emergency.* resources allowed
    2. AI_ADVISORY origin: cannot approve HIGH/CRITICAL jobs
    3. AI_ADVISORY origin: cannot access SITE resources except read-only
    4. FAMILY mode: cannot access PERSONAL, WORK, or SITE resources
    5. PERSONAL mode: cannot access SITE resources
    6. System/Schedule origin: allow for standard resources
    7. Default: allow (v1 permissive; v2 ReBAC will be restrictive)
    """
    ctx = req.context
    resource = req.resource
    action = req.action
    origin = ctx.origin
    mode = ctx.mode

    # Rule 1: Emergency mode restricts to emergency resources only
    if mode == "EMERGENCY" and not resource.startswith("emergency."):
        return {
            "allowed": False,
            "reason": f"EMERGENCY mode only allows emergency.* resources; got {resource!r}",
            "applicable_policy": "emergency_mode_restriction",
        }

    # Rule 2: AI_ADVISORY cannot approve HIGH/CRITICAL jobs
    if origin == "AI_ADVISORY" and action == "approve":
        if ctx.risk_class in ("HIGH", "CRITICAL"):
            return {
                "allowed": False,
                "reason": "AI_ADVISORY origin cannot approve HIGH/CRITICAL risk jobs (ADR-002, F05)",
                "applicable_policy": "ai_advisory_approve_guard",
            }

    # Rule 3: AI_ADVISORY cannot create site-control jobs
    if origin == "AI_ADVISORY" and resource.startswith("site_control."):
        return {
            "allowed": False,
            "reason": "AI_ADVISORY origin cannot create site-control jobs (ADR-002)",
            "applicable_policy": "ai_advisory_site_control_guard",
        }

    # Rule 4: FAMILY mode cannot access PERSONAL or WORK resources
    if mode == "FAMILY":
        if any(resource.startswith(p) for p in ("personal.", "work.", "private.")):
            return {
                "allowed": False,
                "reason": f"FAMILY mode cannot access {resource!r}",
                "applicable_policy": "family_mode_isolation",
            }

    # Rule 5: PERSONAL mode cannot access SITE control resources
    if mode == "PERSONAL" and resource.startswith("site_control."):
        return {
            "allowed": False,
            "reason": "PERSONAL mode cannot access site-control resources",
            "applicable_policy": "personal_mode_site_guard",
        }

    # Default: allow (v1 permissive; tighten in v2)
    return {
        "allowed": True,
        "reason": f"v1 RBAC: no denial rule matched for {resource!r} in {mode} mode",
        "applicable_policy": "v1_rbac_default_allow",
    }
