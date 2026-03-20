"""
MCP Gateway Policy Engine

Evaluates whether a tool invocation is allowed given the full ExecutionContext.

IMPORTANT: risk_class and trust_tier are DIFFERENT AXES.
- risk_class: classification of the REQUEST (LOW/MEDIUM/HIGH/CRITICAL)
- trust_tier: classification of the TOOL (T0-T4), indicating what contexts can invoke it

A HIGH-risk request does not automatically match a T4 tool.
A policy function evaluates the combination of: tool tier, request mode,
request origin, request risk_class, and user role.

Reference: docs/architecture/kernel-authority-model.md (mcp-gateway row)
ADR: ADR-018 (Tool Fabric Plane), ADR-019 (Authorization Evolution)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TrustTier(str, Enum):
    """
    Tool trust tiers. Describes the minimum context required to invoke a tool.
    NOT the same as risk_class. Do not compare them with ordering operators.

    T0 — Public informational: no auth required (weather, time, public data)
    T1 — Household informational: family-authenticated (calendar, shopping list, crop status read)
    T2 — Personal sensitive: individual-authenticated (personal notes, health data)
    T3 — Site read-only: operator context, no actuation (sensor readings, job status)
    T4 — Site operational: operator context, site-control adjacent (configuration, reporting)
    """
    T0 = "T0"   # Public informational
    T1 = "T1"   # Household informational
    T2 = "T2"   # Personal sensitive
    T3 = "T3"   # Site read-only
    T4 = "T4"   # Site operational (adjacent to control; never direct actuation)


# Tools registered as T5 (direct site actuation) are NEVER registered.
# Drone arming is never a registered tool. (ADR-002, ADR-005)


@dataclass
class ToolDescriptor:
    """Metadata for a registered MCP tool."""
    name: str
    description: str
    trust_tier: TrustTier
    domain: str          # "personal" | "household" | "work" | "site"
    surfaces: list[str]  # Surfaces the tool is available on
    output_schema: dict[str, Any]  # MCP 2025 outputSchema for structuredContent
    title: str = ""      # MCP 2025 title metadata


@dataclass
class PolicyRequest:
    """Input to the policy evaluation function."""
    tool: ToolDescriptor
    user_id: str
    mode: str          # Mode value string
    surface: str       # Surface value string
    risk_class: str    # RiskClass value string
    origin: str        # Origin value string
    # Additional context from ExecutionContext
    intent_class: str = ""
    trace_id: str = ""


@dataclass
class PolicyResult:
    """Output of the policy evaluation function."""
    allowed: bool
    reason: str
    applicable_rule: str


def evaluate(request: PolicyRequest) -> PolicyResult:
    """
    Policy function for tool access.

    Evaluates using multiple independent axes:
    1. Drone arm guard (ADR-002, ADR-005) — hard deny, always
    2. AI_ADVISORY origin guard — AI cannot invoke T3/T4 tools directly
    3. Mode-tier compatibility — mode must satisfy the tool's minimum tier
    4. Surface availability — tool must be available on the request surface
    5. Site-actuation guard — T4 tools only in SITE or WORK mode with operator origin

    Returns PolicyResult with allowed=True if all rules pass.
    """
    tool = request.tool

    # Rule 1: Drone arm is never allowed through MCP. Ever.
    if "drone" in tool.name.lower() and "arm" in tool.name.lower():
        return PolicyResult(
            allowed=False,
            reason="Drone arming is never a registered MCP tool (ADR-002, ADR-005)",
            applicable_rule="drone_arm_hard_deny",
        )

    # Rule 2: AI_ADVISORY cannot invoke T3/T4 tools
    # AI may propose actions; it must not directly access site-adjacent tools
    if request.origin == "AI_ADVISORY" and tool.trust_tier in (TrustTier.T3, TrustTier.T4):
        return PolicyResult(
            allowed=False,
            reason=f"AI_ADVISORY origin cannot invoke {tool.trust_tier.value} tools (ADR-002)",
            applicable_rule="ai_advisory_tier_guard",
        )

    # Rule 3: Mode-tier compatibility
    # This is NOT a simple comparison — it's a set of named rules
    mode_rule = _check_mode_tier_compatibility(request.mode, tool.trust_tier)
    if not mode_rule.allowed:
        return mode_rule

    # Rule 4: Surface availability
    if request.surface not in tool.surfaces and "*" not in tool.surfaces:
        return PolicyResult(
            allowed=False,
            reason=f"Tool '{tool.name}' is not available on surface '{request.surface}'",
            applicable_rule="surface_availability",
        )

    # Rule 5: T4 tools require SITE or WORK mode AND non-AI_ADVISORY origin
    if tool.trust_tier == TrustTier.T4:
        if request.mode not in ("SITE", "WORK"):
            return PolicyResult(
                allowed=False,
                reason=f"T4 tools require SITE or WORK mode; current mode is {request.mode}",
                applicable_rule="t4_mode_guard",
            )
        if request.origin == "AI_ADVISORY":
            return PolicyResult(
                allowed=False,
                reason="T4 tools require OPERATOR or SYSTEM origin",
                applicable_rule="t4_origin_guard",
            )

    return PolicyResult(
        allowed=True,
        reason=f"Policy allows {tool.name} ({tool.trust_tier.value}) in {request.mode} mode",
        applicable_rule="default_allow",
    )


def _check_mode_tier_compatibility(mode: str, tier: TrustTier) -> PolicyResult:
    """
    Named rules for mode-tier compatibility.
    These are business rules, not an ordering comparison.
    """
    # T0: available in all modes (public information)
    if tier == TrustTier.T0:
        return PolicyResult(allowed=True, reason="T0 tools are always available",
                            applicable_rule="t0_always_available")

    # T1: requires FAMILY, PERSONAL, WORK, or SITE mode (not EMERGENCY)
    if tier == TrustTier.T1:
        if mode == "EMERGENCY":
            return PolicyResult(
                allowed=False,
                reason="T1 household tools suppressed in EMERGENCY mode",
                applicable_rule="t1_emergency_suppress",
            )
        return PolicyResult(allowed=True, reason="T1 allowed in household+ modes",
                            applicable_rule="t1_household_allow")

    # T2: requires PERSONAL, WORK, or SITE mode (not FAMILY or EMERGENCY)
    # FAMILY mode cannot access personal-sensitive data
    if tier == TrustTier.T2:
        if mode in ("FAMILY", "EMERGENCY"):
            return PolicyResult(
                allowed=False,
                reason=f"T2 personal-sensitive tools not available in {mode} mode",
                applicable_rule="t2_mode_guard",
            )
        return PolicyResult(allowed=True, reason="T2 allowed in personal+ modes",
                            applicable_rule="t2_personal_allow")

    # T3: requires SITE, WORK mode (site-readonly access)
    if tier == TrustTier.T3:
        if mode not in ("SITE", "WORK"):
            return PolicyResult(
                allowed=False,
                reason=f"T3 site-readonly tools require SITE or WORK mode; current: {mode}",
                applicable_rule="t3_mode_guard",
            )
        return PolicyResult(allowed=True, reason="T3 allowed in site/work modes",
                            applicable_rule="t3_site_allow")

    # T4: handled in evaluate() — extra origin check there
    return PolicyResult(allowed=True, reason="T4 base mode check passed",
                        applicable_rule="t4_base_allow")
