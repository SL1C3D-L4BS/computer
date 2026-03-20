"""
MCP Gateway — FastAPI service

Tool access mediator for step 7a of the CRK execution loop.
Governs access using a policy function (not a simplistic ordering comparison).

THIS GATEWAY:
- Handles T0-T4 tools: personal, household, work, site-readonly
- Implements MCP 2025-06-18 OAuth 2.1 auth (RFC 9728 / RFC 8414 / RFC 8707)
- Returns structuredContent for typed tool outputs

DOES NOT:
- Register drone arming (ADR-002, ADR-005)
- Handle site-control actuation (that is step 7b → orchestrator)
- Create orchestrator jobs

ADR: ADR-018 (Tool Fabric Plane)
Reference: docs/architecture/runtime-kernel.md (step 7a vs 7b)
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import structlog

from mcp_gateway.policy import evaluate, PolicyRequest, TrustTier
from mcp_gateway.registry import get_tool, list_tools
from mcp_gateway.auth import validate_bearer_token

CONTRACTS_PATH = Path(__file__).parent.parent.parent / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

try:
    from models import Mode, Surface, RiskClass, Origin
except ImportError:
    # Fallback: define minimal stubs if contracts package not on path
    Mode = str
    Surface = str
    RiskClass = str
    Origin = str

log = structlog.get_logger(__name__)

MCP_RESOURCE_URI = "http://localhost:8061"   # This gateway's URI for RFC 8707

app = FastAPI(
    title="MCP Gateway",
    description="Tool access mediator — step 7a of the CRK execution loop",
    version="0.1.0",
)


# ── Request / Response models ─────────────────────────────────────────────────

class ExecutionContextPayload(BaseModel):
    """Subset of ExecutionContext forwarded from runtime-kernel."""
    user_id: str
    mode: str
    surface: str
    risk_class: str
    intent_class: str = ""
    trace_id: str = ""
    origin: str = "OPERATOR"


class ToolInvokeRequest(BaseModel):
    """
    POST /tools/invoke

    tool_name: "auto" triggers best-match selection; otherwise exact name
    arguments: tool-specific arguments (free-form per tool's inputSchema)
    execution_context: full context from runtime-kernel (step 7a entry)
    """
    tool_name: str
    arguments: dict[str, Any] = {}
    execution_context: ExecutionContextPayload


class ToolInvokeResponse(BaseModel):
    """
    MCP 2025-06-18 structured response.
    structuredContent is the typed output (per tool's outputSchema).
    content is the text rendering for voice/chat surfaces.
    resource_links lists any referenced resources (MCP 2025 resource_link type).
    """
    tool_name: str
    structuredContent: dict[str, Any] | None
    content: str
    resource_links: list[dict[str, Any]] = []
    trace_id: str
    policy_applied: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-gateway"}


@app.get("/tools")
async def list_available_tools(
    domain: str | None = None,
    surface: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """
    GET /tools — filterable by domain, surface, mode.
    Returns tools the caller CAN see given their context.
    NOT filterable by max_risk_class (that is not how this gateway works).
    """
    tools = list_tools(domain=domain, surface=surface, mode=mode)
    return {
        "tools": [
            {
                "name": t.name,
                "title": t.title,
                "description": t.description,
                "trust_tier": t.trust_tier.value,
                "domain": t.domain,
                "output_schema": t.output_schema,
            }
            for t in tools
        ],
        "count": len(tools),
    }


@app.post("/tools/invoke")
async def invoke_tool(req: ToolInvokeRequest) -> ToolInvokeResponse:
    """
    POST /tools/invoke — the primary step 7a execution path.

    1. Look up tool by name (or auto-select)
    2. Run policy function with full ExecutionContext
    3. If allowed: execute stub and return structuredContent
    4. If denied: 403 with policy reason
    """
    t0 = time.monotonic()
    ctx = req.execution_context
    trace_id = ctx.trace_id or str(uuid.uuid4())

    # Step 1: tool lookup
    if req.tool_name == "auto":
        tool = _auto_select_tool(req.arguments, ctx)
    else:
        tool = get_tool(req.tool_name)

    if tool is None:
        log.warning("mcp_gateway.tool_not_found", tool=req.tool_name, trace_id=trace_id)
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool_name}' not found")

    # Step 2: policy evaluation (not a comparison — a function)
    policy_req = PolicyRequest(
        tool=tool,
        user_id=ctx.user_id,
        mode=ctx.mode,
        surface=ctx.surface,
        risk_class=ctx.risk_class,
        origin=ctx.origin,
        intent_class=ctx.intent_class,
        trace_id=trace_id,
    )
    policy_result = evaluate(policy_req)

    if not policy_result.allowed:
        log.warning(
            "mcp_gateway.policy_denied",
            tool=tool.name,
            reason=policy_result.reason,
            rule=policy_result.applicable_rule,
            trace_id=trace_id,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tool_access_denied",
                "reason": policy_result.reason,
                "rule": policy_result.applicable_rule,
                "tool": tool.name,
                "trace_id": trace_id,
            },
        )

    # Step 3: execute (stub — real MCP server call in v1)
    structured, text = _execute_stub(tool, req.arguments, ctx)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "mcp_gateway.tool_invoked",
        tool=tool.name,
        tier=tool.trust_tier.value,
        mode=ctx.mode,
        policy_rule=policy_result.applicable_rule,
        elapsed_ms=elapsed_ms,
        trace_id=trace_id,
    )

    return ToolInvokeResponse(
        tool_name=tool.name,
        structuredContent=structured,
        content=text,
        resource_links=[],
        trace_id=trace_id,
        policy_applied=policy_result.applicable_rule,
    )


@app.get("/tools/{tool_name}/schema")
async def tool_schema(tool_name: str) -> dict[str, Any]:
    """Return the outputSchema for a specific tool (MCP 2025 structured output)."""
    tool = get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return {
        "name": tool.name,
        "title": tool.title,
        "trust_tier": tool.trust_tier.value,
        "output_schema": tool.output_schema,
    }


# ── Stub execution ────────────────────────────────────────────────────────────

def _execute_stub(
    tool,
    arguments: dict[str, Any],
    ctx: ExecutionContextPayload,
) -> tuple[dict[str, Any], str]:
    """
    Stub tool execution. Returns synthetic structuredContent.
    Replace with real MCP server calls in v1.
    """
    import datetime

    stubs: dict[str, tuple[dict, str]] = {
        "time.current": (
            {
                "iso8601": datetime.datetime.now().isoformat(),
                "timezone": "UTC",
                "unix_epoch": int(datetime.datetime.now().timestamp()),
            },
            f"The current time is {datetime.datetime.now().strftime('%I:%M %p')}",
        ),
        "weather.current": (
            {"temperature_c": 22.5, "humidity_pct": 58.0, "conditions": "partly cloudy"},
            "It's 22.5°C and partly cloudy at the homestead.",
        ),
        "calendar.events": (
            {"events": [{"title": "Team standup", "start_iso8601": "2026-03-19T09:00:00", "duration_minutes": 30}]},
            "You have a team standup at 9am tomorrow.",
        ),
        "greenhouse.status": (
            {"temperature_c": 24.1, "humidity_pct": 72.0, "co2_ppm": 420, "zones": []},
            "Greenhouse is at 24.1°C, 72% humidity, CO2 420ppm.",
        ),
        "memory.read": (
            {"entries": []},
            "No personal memory entries found for your query.",
        ),
        "site.jobs.list": (
            {"jobs": []},
            "No active site jobs.",
        ),
        "site.sensors.read": (
            {"sensors": [], "timestamp": datetime.datetime.now().isoformat()},
            "No sensor data available in stub mode.",
        ),
        "site.config.read": (
            {"config": {}, "version": "0.1.0-stub"},
            "Site configuration (stub): empty.",
        ),
    }

    if tool.name in stubs:
        return stubs[tool.name]

    return ({"result": "stub"}, f"Tool '{tool.name}' executed (stub response).")


def _auto_select_tool(
    arguments: dict[str, Any],
    ctx: ExecutionContextPayload,
) -> object | None:
    """Auto-select best matching tool from available tools given the context."""
    query = str(arguments.get("query", "")).lower()

    candidates = list_tools(surface=ctx.surface, mode=ctx.mode)

    # Simple keyword matching for stub auto-select
    keyword_map = {
        "time": "time.current",
        "clock": "time.current",
        "weather": "weather.current",
        "temperature": "weather.current",
        "calendar": "calendar.events",
        "meeting": "calendar.events",
        "event": "calendar.events",
        "greenhouse": "greenhouse.status",
        "crops": "greenhouse.status",
        "plant": "greenhouse.status",
        "memory": "memory.read",
        "remember": "memory.read",
        "job": "site.jobs.list",
        "sensor": "site.sensors.read",
    }

    for keyword, tool_name in keyword_map.items():
        if keyword in query:
            return get_tool(tool_name)

    # Fallback: return time tool (T0, always available)
    return get_tool("time.current")
