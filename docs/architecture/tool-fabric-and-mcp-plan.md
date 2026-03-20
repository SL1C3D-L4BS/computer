# Tool Fabric and MCP Plan

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-018 (Tool Fabric Plane), ADR-026 (MCP as universal step 7a interface)  
**Implementation:** `packages/mcp-gateway/`

---

## MCP 2025-06-18 as System Spine

The Model Context Protocol (MCP) 2025-06-18 is the universal tool interface for **CRK step 7a**. Every tool invocation for personal, household, work, and site-readonly access goes through the MCP protocol via `mcp-gateway`.

MCP 2025-06-18 key features used:

| Feature | Usage |
|---------|-------|
| `outputSchema` / `structuredContent` | Typed tool outputs for downstream parsing and UI rendering |
| OAuth 2.1 resource server model | Authorization discovery chain (RFC 9728 / RFC 8414 / RFC 8707) |
| Elicitation (`elicitation/create`) | Server → user mid-execution input requests, routed through attention-engine |
| `resource_link` content type | References to external resources in responses |
| `title` metadata | Human-readable tool names for UI display |
| JSON-RPC batch **REMOVED** | Not used; per MCP 2025-06-18 spec |

---

## Step 7a Definition

Step 7a of the CRK execution loop handles tool invocations for **low-to-medium consequence** requests.

**What goes through step 7a:**
- Personal information retrieval (T2 and below)
- Household shared information (T1)
- Site read-only queries (T3)
- Site operational non-actuation (T4)

**What NEVER goes through step 7a:**
- Site-control actuation (valve opens, heater enable, robot arm, lock toggle)
- Any action that modifies physical site state
- Orchestrator job creation or approval

The boundary is not risk_class — it is the semantic distinction between **information/advisory tools** and **control-plane actuation**.

---

## OAuth 2.1 Authorization Discovery Chain

When a tool invocation receives a 401 response from an MCP server:

```
Step 1: GET {resource_uri}/.well-known/oauth-protected-resource  (RFC 9728)
        Response: { "authorization_servers": ["https://auth.computer.local"] }

Step 2: GET https://auth.computer.local/.well-known/oauth-authorization-server  (RFC 8414)
        Response: {
            "issuer": "https://auth.computer.local",
            "authorization_endpoint": "https://auth.computer.local/authorize",
            "token_endpoint": "https://auth.computer.local/token",
            "code_challenge_methods_supported": ["S256"]
        }

Step 3: PKCE flow (RFC 7636, required by OAuth 2.1)
        - Generate code_verifier (random 40-byte hex)
        - code_challenge = base64url(SHA256(code_verifier))
        - Redirect to authorization_endpoint with code_challenge

Step 4: Exchange code for token at token_endpoint

Step 5: Validate token audience (RFC 8707)
        - token.aud must contain mcp-gateway resource URI
        - Prevents token replay across different resource servers
```

Implementation: `packages/mcp-gateway/mcp_gateway/auth.py`

---

## Policy Function

The `mcp-gateway` uses a **policy function**, not an ordering comparison.

```python
# WRONG — do not do this:
if request.risk_class < tool.trust_tier:   # ← NEVER
    allow()

# CORRECT — policy function:
result = policy.evaluate(PolicyRequest(
    tool=tool,
    user_id=ctx.user_id,
    mode=ctx.mode,       # ← mode required
    surface=ctx.surface,
    risk_class=ctx.risk_class,
    origin=ctx.origin,   # ← AI_ADVISORY has special rules
))
```

**Why:** `risk_class` characterizes the **request** (how consequential is this action?). `trust_tier` characterizes the **tool** (what context is required to use it?). They are orthogonal dimensions. A LOW-risk request can be made in EMERGENCY mode (which restricts T1+ tools). A HIGH-risk request doesn't automatically grant T4 access.

Policy rules (evaluated in order):
1. Drone arm guard — always deny (ADR-002, ADR-005)
2. AI_ADVISORY + T3/T4 — deny (AI may not access site-adjacent tools)
3. Mode-tier compatibility — named rules per (mode, tier) pair
4. Surface availability — tool must be declared for the surface
5. T4 mode+origin guard — SITE/WORK mode AND non-AI_ADVISORY origin

---

## Tool Registry Structure

Tools are declared in `packages/mcp-gateway/mcp_gateway/registry.py`:

```python
ToolDescriptor(
    name="greenhouse.status",
    title="Greenhouse Status",          # MCP 2025 title metadata
    description="...",
    trust_tier=TrustTier.T1,
    domain="household",
    surfaces=["VOICE", "CHAT", "WEB", "MOBILE", "OPS"],
    output_schema={                      # MCP 2025 outputSchema
        "type": "object",
        "properties": {
            "temperature_c": {"type": "number"},
            ...
        }
    }
)
```

**Never registered:**
- `drone.arm` (ADR-002, ADR-005)
- `valve.open`, `heater.enable`, `gate.unlock` — these are orchestrator jobs
- Any T5 (direct hardware actuation) tool

---

## Why Step 7b NEVER Goes Through mcp-gateway

Step 7b (control job binding) creates orchestrator jobs for HIGH-consequence site-control. This is architecturally distinct from tool invocation:

| Dimension | Step 7a (mcp-gateway) | Step 7b (orchestrator) |
|-----------|----------------------|------------------------|
| Reversibility | Mostly reversible (read/compute) | Irreversible or physical-world impact |
| Audit trail | MCP structured output + trace | Full job state machine audit |
| Approval | Policy function (immediate) | Approval gates for HIGH/CRITICAL |
| Failure mode | Return error content | Job enters FAILED state; alert sent |
| MQTT | Never | Only output pathway to hardware |
| AI role | May be invoked by AI_ADVISORY for T0-T2 | AI_ADVISORY may only PROPOSE, never submit |

Routing a valve command through the tool layer would:
1. Bypass the orchestrator state machine (audit gap)
2. Bypass approval gates
3. Allow AI to directly actuate hardware (ADR-002 violation)

**The mcp-gateway is a tool bus, not a control bus.**

---

## Elicitation

When an MCP server needs user input mid-execution (`elicitation/create` per MCP 2025-06-18):

1. `mcp-gateway` receives the elicitation request
2. Routes it to `attention-engine` as an INTERRUPT with the user prompt
3. User provides input via the appropriate surface
4. `mcp-gateway` completes the tool invocation with the input

This preserves the step 9 attention model — even mid-tool interrupts go through the attention engine.

---

## Packages

| Package | Purpose |
|---------|---------|
| `packages/mcp-gateway/` | Policy engine, registry, auth, FastAPI service |
| `packages/mcp-tools/` (Phase 2) | MCP tool definitions with `outputSchema` and T0-T4 annotations |
| `packages/mcp-servers/` (Phase 2) | Internal MCP server stubs: repo, family, site-readonly, ops-guarded |
