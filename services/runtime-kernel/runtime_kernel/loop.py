"""
CRK Execution Loop — the 10-step lifecycle.

Each step is a discrete function. Steps that are no-ops return quickly.
Steps that fail degrade gracefully except step 6 (auth), which hard-denies.

Reference: docs/architecture/runtime-kernel.md
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import structlog

# Import shared contracts (adjust path for monorepo layout)
CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

from models import (
    AttentionAction,
    AttentionDecision,
    AttentionPriority,
    AuthzContext,
    AuthzRequest,
    AuthzResponse,
    Channel,
    ComputerState,
    ExecutionContext,
    InputEnvelope,
    MemoryScope,
    Mode,
    Origin,
    ResponseEnvelope,
    RiskClass,
    StepAuditRecord,
    Surface,
    WorkflowBinding,
    WorkflowBindingType,
)

log = structlog.get_logger(__name__)

# ── Service URLs ──────────────────────────────────────────────────────────────
import os

CONTEXT_ROUTER_URL  = os.getenv("CONTEXT_ROUTER_URL",  "http://localhost:8030")
MODEL_ROUTER_URL    = os.getenv("MODEL_ROUTER_URL",     "http://localhost:8020")
WORKFLOW_RUNTIME_URL= os.getenv("WORKFLOW_RUNTIME_URL", "http://localhost:8050")
AUTHZ_SERVICE_URL   = os.getenv("AUTHZ_SERVICE_URL",    "http://localhost:8060")
MCP_GATEWAY_URL     = os.getenv("MCP_GATEWAY_URL",      "http://localhost:8061")
ORCHESTRATOR_URL    = os.getenv("ORCHESTRATOR_URL",     "http://localhost:8002")
ATTENTION_ENGINE_URL= os.getenv("ATTENTION_ENGINE_URL", "http://localhost:8062")

_http = httpx.AsyncClient(timeout=8.0)

# ── Audit log (in-memory for stub; replace with Postgres in v1) ──────────────
_audit_log: list[StepAuditRecord] = []


def _audit(
    ctx: ExecutionContext,
    step: str,
    status: str,
    detail: str,
    duration_ms: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    record = StepAuditRecord(
        request_id=ctx.request_id,
        trace_id=ctx.trace_id,
        step=step,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        metadata=metadata or {},
    )
    _audit_log.append(record)
    log.info("crk.step", step=step, status=status, trace_id=ctx.trace_id,
             request_id=ctx.request_id, detail=detail)


def get_audit_log() -> list[StepAuditRecord]:
    return list(_audit_log)


# ── Step 1: Input Ingestion ───────────────────────────────────────────────────

def step1_ingest(envelope: InputEnvelope) -> ExecutionContext:
    """Normalize InputEnvelope into ExecutionContext. Always runs."""
    ctx = ExecutionContext(
        request_id=str(uuid.uuid4()),
        user_id=envelope.user_id,
        mode=_default_mode_for_surface(envelope.surface),
        surface=envelope.surface,
        intent_class="unknown",
        memory_scope=_default_memory_scope(envelope.surface),
        active_workflow_ids=[],
        risk_class=RiskClass.LOW,
        origin=Origin.OPERATOR,
        trace_id=envelope.trace_id,
        session_id=envelope.session_id,
        attention_load=0.0,
    )
    _audit(ctx, "1_input_ingestion", "ok", f"surface={envelope.surface}, user={envelope.user_id}")
    return ctx


def _default_mode_for_surface(surface: Surface) -> Mode:
    return {
        Surface.VOICE:  Mode.PERSONAL,
        Surface.CHAT:   Mode.PERSONAL,
        Surface.WEB:    Mode.FAMILY,
        Surface.MOBILE: Mode.PERSONAL,
        Surface.OPS:    Mode.SITE,
        Surface.EVENT:  Mode.SITE,
    }.get(surface, Mode.PERSONAL)


def _default_memory_scope(surface: Surface) -> MemoryScope:
    return {
        Surface.OPS:   MemoryScope.SITE,
        Surface.EVENT: MemoryScope.SITE,
        Surface.WEB:   MemoryScope.HOUSEHOLD_SHARED,
    }.get(surface, MemoryScope.PERSONAL)


# ── Step 2: Intent Classification ────────────────────────────────────────────

async def step2_classify(ctx: ExecutionContext, raw_input: str) -> ExecutionContext:
    """Classify intent. Stub: pattern matching for test coverage."""
    t0 = time.monotonic()
    intent = _classify_intent_stub(raw_input)
    risk = _classify_risk_stub(intent)

    ctx = _enrich(ctx, intent_class=intent, risk_class=risk)
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "2_intent_classification", "stub",
           f"intent={intent}, risk={risk}", ms)
    return ctx


def _classify_intent_stub(raw: str) -> str:
    r = raw.lower()
    if any(w in r for w in ["valve", "heat", "arm", "irrigation", "unlock", "actuate"]):
        return "site_control.actuate"
    if any(w in r for w in ["rover", "drone", "mission"]):
        return "robotics.mission"
    if any(w in r for w in ["remind", "schedule", "later", "tomorrow"]):
        return "workflow.schedule"
    if any(w in r for w in ["emergency", "stop", "estop", "e-stop", "alarm"]):
        return "emergency.interrupt"
    return "assistant.query"


def _classify_risk_stub(intent: str) -> RiskClass:
    if "site_control.actuate" in intent or "robotics.mission" in intent:
        return RiskClass.HIGH
    if "emergency" in intent:
        return RiskClass.CRITICAL
    return RiskClass.LOW


# ── Step 3: Context Resolution ────────────────────────────────────────────────

async def step3_resolve_context(
    ctx: ExecutionContext,
    mode_map: dict[str, Mode],
) -> ExecutionContext:
    """
    Resolve full context from context-router.
    Stub: uses sticky mode map.
    """
    t0 = time.monotonic()
    sticky_key = f"{ctx.user_id}:{ctx.surface}"
    resolved_mode = mode_map.get(sticky_key, ctx.mode)

    # Try real service; fall back to stub
    try:
        r = await _http.post(f"{CONTEXT_ROUTER_URL}/resolve", json={
            "user_id": ctx.user_id,
            "mode": resolved_mode,
            "message": "",
            "surface": ctx.surface,
        }, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            resolved_mode = Mode(data.get("mode", resolved_mode))
            ctx = _enrich(ctx, mode=resolved_mode,
                          memory_scope=MemoryScope(data.get("memory_scope", ctx.memory_scope)))
            ms = int((time.monotonic() - t0) * 1000)
            _audit(ctx, "3_context_resolution", "ok",
                   f"mode={resolved_mode} (from context-router)", ms)
            return ctx
    except Exception:
        pass  # Fall through to stub

    ctx = _enrich(ctx, mode=resolved_mode)
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "3_context_resolution", "stub",
           f"mode={resolved_mode} (from sticky map)", ms)
    return ctx


# ── Step 4: Plan Generation ───────────────────────────────────────────────────

async def step4_plan(ctx: ExecutionContext, raw_input: str) -> ExecutionContext:
    """
    Determine: AI proposal or deterministic policy path.
    Stub: deterministic for HIGH/CRITICAL; AI for LOW.
    """
    t0 = time.monotonic()
    if ctx.risk_class in (RiskClass.HIGH, RiskClass.CRITICAL):
        plan_type = "deterministic_policy"
    else:
        plan_type = "ai_proposal"
    ctx = _enrich(ctx, plan_type=plan_type)
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "4_plan_generation", "stub", f"plan_type={plan_type}", ms)
    return ctx


# ── Step 5: Workflow Binding ─────────────────────────────────────────────────

async def step5_bind_workflow(ctx: ExecutionContext) -> ExecutionContext:
    """
    Decide: durable Temporal workflow or immediate execution.
    Stub: DURABLE for schedule intents; IMMEDIATE otherwise.
    """
    t0 = time.monotonic()
    if "workflow.schedule" in ctx.intent_class or "workflow" in ctx.intent_class:
        wf_id = f"wf-{ctx.request_id}"
        binding = WorkflowBinding(
            workflow_id=wf_id,
            type=WorkflowBindingType.DURABLE,
            temporal_task_queue="computer-main",
        )
        _type = "DURABLE"
    else:
        binding = WorkflowBinding(
            workflow_id=f"imm-{ctx.request_id}",
            type=WorkflowBindingType.IMMEDIATE,
        )
        _type = "IMMEDIATE"

    ctx = _enrich(ctx, workflow_binding=binding)
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "5_workflow_binding", "stub", f"type={_type}, id={binding.workflow_id}", ms)
    return ctx


# ── Step 6: Authorization Check ──────────────────────────────────────────────

async def step6_authorize(ctx: ExecutionContext) -> AuthzResponse:
    """
    HARD GATE: if auth fails or times out, halt. Never allow on auth failure.
    This is the only step that returns a value other than ctx.
    """
    t0 = time.monotonic()
    authz_req = AuthzRequest(
        subject=ctx.user_id,
        resource=ctx.intent_class,
        action="execute",
        context=AuthzContext(
            mode=ctx.mode,
            risk_class=ctx.risk_class,
            origin=ctx.origin,
        ),
    )

    try:
        r = await _http.post(f"{AUTHZ_SERVICE_URL}/authorize", json={
            "subject": authz_req.subject,
            "resource": authz_req.resource,
            "action": authz_req.action,
            "context": {
                "mode": authz_req.context.mode,
                "risk_class": authz_req.context.risk_class,
                "origin": authz_req.context.origin,
            },
        }, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            resp = AuthzResponse(
                allowed=data["allowed"],
                reason=data.get("reason", ""),
                applicable_policy=data.get("applicable_policy", ""),
            )
            ms = int((time.monotonic() - t0) * 1000)
            _audit(ctx, "6_authz_check", "ok" if resp.allowed else "deny",
                   f"allowed={resp.allowed}, policy={resp.applicable_policy}", ms)
            return resp
    except Exception:
        pass

    # Stub: allow all with audit note
    ms = int((time.monotonic() - t0) * 1000)
    resp = AuthzResponse(allowed=True, reason="stub_allow_all",
                         applicable_policy="stub:allow_all")
    _audit(ctx, "6_authz_check", "stub", "stub_allow_all (authz-service not reachable)", ms)
    return resp


# ── Step 7a: Tool Invocation ──────────────────────────────────────────────────

async def step7a_invoke_tool(
    ctx: ExecutionContext,
    raw_input: str,
) -> dict[str, Any] | None:
    """
    MCP tool invocation for personal/family/work/site-readonly requests.
    Returns structuredContent or None if no tool applies.
    7a is NEVER used for site-control actuation (that is 7b).
    """
    if ctx.risk_class in (RiskClass.HIGH, RiskClass.CRITICAL):
        _audit(ctx, "7a_tool_invocation", "noop",
               "HIGH/CRITICAL risk → 7b path; 7a skipped")
        return None

    t0 = time.monotonic()
    try:
        r = await _http.post(f"{MCP_GATEWAY_URL}/tools/invoke", json={
            "tool_name": "auto",
            "arguments": {"query": raw_input},
            "execution_context": {
                "user_id": ctx.user_id,
                "mode": ctx.mode,
                "surface": ctx.surface,
                "risk_class": ctx.risk_class,
                "intent_class": ctx.intent_class,
                "trace_id": ctx.trace_id,
            },
        }, timeout=5.0)
        if r.status_code == 200:
            ms = int((time.monotonic() - t0) * 1000)
            _audit(ctx, "7a_tool_invocation", "ok", f"tool response received", ms)
            return r.json()
    except Exception:
        pass

    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "7a_tool_invocation", "stub",
           "mcp-gateway not reachable; returning stub response", ms)
    return {"structuredContent": None, "content": "", "resource_links": []}


# ── Step 7b: Control Job Binding ─────────────────────────────────────────────

async def step7b_bind_control_job(ctx: ExecutionContext) -> list[str]:
    """
    Creates orchestrator jobs for HIGH-consequence site-control requests.
    Returns list of job IDs created. Empty list = 7b was a no-op.
    7b is NEVER called for personal/family/work/site-readonly requests.
    """
    if ctx.risk_class not in (RiskClass.HIGH, RiskClass.CRITICAL):
        _audit(ctx, "7b_control_job_bind", "noop",
               "LOW/MEDIUM risk → 7a path; 7b skipped")
        return []

    if ctx.intent_class == "emergency.interrupt":
        # Emergency: handled via /interrupt endpoint, not job submission
        _audit(ctx, "7b_control_job_bind", "noop",
               "emergency intent handled via /interrupt, not job submission")
        return []

    t0 = time.monotonic()
    try:
        r = await _http.post(f"{ORCHESTRATOR_URL}/jobs", json={
            "type": ctx.intent_class,
            "origin": ctx.origin,
            "risk_class": ctx.risk_class,
            "requested_by": ctx.user_id,
            "parameters": {"trace_id": ctx.trace_id},
        }, headers={"Authorization": "Bearer dev-token"}, timeout=5.0)
        if r.status_code in (200, 201):
            job_id = r.json().get("id", f"stub-job-{ctx.request_id}")
            ms = int((time.monotonic() - t0) * 1000)
            _audit(ctx, "7b_control_job_bind", "ok",
                   f"job_id={job_id}, risk={ctx.risk_class}", ms)
            return [job_id]
    except Exception:
        pass

    # Stub: return a deterministic stub job ID
    stub_job_id = f"stub-job-{ctx.request_id}"
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "7b_control_job_bind", "stub",
           f"orchestrator not reachable; stub job_id={stub_job_id}", ms)
    return [stub_job_id]


# ── Step 8: State Update ──────────────────────────────────────────────────────

async def step8_update_state(
    ctx: ExecutionContext,
    job_ids: list[str],
    tool_result: dict[str, Any] | None,
) -> None:
    """Write to memory, digital-twin, audit. Stub: log only."""
    _audit(ctx, "8_state_update", "stub",
           f"jobs={job_ids}, tool_result={'present' if tool_result else 'none'}")


# ── Step 9: Attention Decision ────────────────────────────────────────────────

async def step9_attention(ctx: ExecutionContext) -> AttentionDecision:
    """
    Determine how and when to deliver the response.
    Part of execution, not UI (ADR-028).
    """
    t0 = time.monotonic()
    try:
        r = await _http.post(f"{ATTENTION_ENGINE_URL}/evaluate", json={
            "urgency": 1.0 if ctx.risk_class == RiskClass.CRITICAL else 0.5,
            "attention_load": ctx.attention_load,
            "privacy_factor": 0.8 if ctx.mode == Mode.PERSONAL else 1.0,
            "user_id": ctx.user_id,
            "mode": ctx.mode,
        }, timeout=3.0)
        if r.status_code == 200:
            d = r.json()
            decision = AttentionDecision(
                decision=AttentionAction(d.get("decision", "QUEUE")),
                channel=Channel(d.get("channel", "CHAT")),
                audience=d.get("audience", [ctx.user_id]),
                reasoning=d.get("reasoning", ""),
                delay_ms=d.get("delay_ms", 0),
                priority=AttentionPriority(d.get("priority", "NORMAL")),
            )
            ms = int((time.monotonic() - t0) * 1000)
            _audit(ctx, "9_attention_decision", "ok",
                   f"decision={decision.decision}", ms)
            return decision
    except Exception:
        pass

    # Stub
    action = AttentionAction.INTERRUPT if ctx.risk_class == RiskClass.CRITICAL else AttentionAction.QUEUE
    channel = _surface_to_channel(ctx.surface)
    decision = AttentionDecision(
        decision=action,
        channel=channel,
        audience=[ctx.user_id],
        reasoning="stub_attention",
        delay_ms=0,
        priority=AttentionPriority.CRITICAL if ctx.risk_class == RiskClass.CRITICAL
                 else AttentionPriority.NORMAL,
    )
    ms = int((time.monotonic() - t0) * 1000)
    _audit(ctx, "9_attention_decision", "stub", f"decision={action}", ms)
    return decision


# ── Step 10: Response Render ──────────────────────────────────────────────────

def step10_render(
    ctx: ExecutionContext,
    tool_result: dict[str, Any] | None,
    job_ids: list[str],
    attention: AttentionDecision,
) -> ResponseEnvelope:
    """Assemble ResponseEnvelope. trace_id MUST match InputEnvelope.trace_id."""
    if job_ids:
        content = f"Job submitted for approval: {', '.join(job_ids)}"
    elif tool_result and tool_result.get("content"):
        content = str(tool_result["content"])
    else:
        content = "OK"

    resp = ResponseEnvelope(
        content=content,
        channel=attention.channel,
        attention_decision=attention,
        proposed_jobs=job_ids,
        trace_id=ctx.trace_id,   # INVARIANT: must match InputEnvelope.trace_id
        workflow_binding=ctx.workflow_binding,
    )
    _audit(ctx, "10_response_render", "ok",
           f"channel={attention.channel}, jobs={job_ids}, trace_id={ctx.trace_id}")
    return resp


# ── Full Loop ─────────────────────────────────────────────────────────────────

async def execute_loop(
    envelope: InputEnvelope,
    mode_map: dict[str, Mode],
) -> tuple[ResponseEnvelope, ExecutionContext]:
    """
    Run the full 10-step CRK execution loop.
    Returns (ResponseEnvelope, final ExecutionContext).
    Raises ExecutionAuthDeniedError if step 6 denies.
    """
    # Steps 1-5: build and enrich context
    ctx = step1_ingest(envelope)
    ctx = await step2_classify(ctx, envelope.raw_input)
    ctx = await step3_resolve_context(ctx, mode_map)
    ctx = await step4_plan(ctx, envelope.raw_input)
    ctx = await step5_bind_workflow(ctx)

    # Step 6: HARD GATE — auth failure halts
    authz = await step6_authorize(ctx)
    if not authz.allowed:
        _audit(ctx, "6_authz_check", "deny",
               f"DENIED: {authz.reason}, policy={authz.applicable_policy}")
        raise ExecutionAuthDeniedError(
            f"Authorization denied: {authz.reason}"
        )

    # Steps 7a/7b: mutually exclusive paths based on risk_class
    tool_result = await step7a_invoke_tool(ctx, envelope.raw_input)
    job_ids = await step7b_bind_control_job(ctx)

    # Steps 8-10
    await step8_update_state(ctx, job_ids, tool_result)
    attention = await step9_attention(ctx)
    response = step10_render(ctx, tool_result, job_ids, attention)

    return response, ctx


class ExecutionAuthDeniedError(Exception):
    """Raised when step 6 denies the request. Always halt, never swallow."""
    pass


def _surface_to_channel(surface: Surface) -> Channel:
    """Map surface to the natural output channel."""
    return {
        Surface.VOICE:  Channel.VOICE,
        Surface.CHAT:   Channel.WEB,
        Surface.WEB:    Channel.WEB,
        Surface.MOBILE: Channel.MOBILE,
        Surface.OPS:    Channel.OPS,
        Surface.EVENT:  Channel.OPS,
    }.get(surface, Channel.WEB)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _enrich(ctx: ExecutionContext, **kwargs) -> ExecutionContext:
    """Return a new ExecutionContext with updated fields."""
    from dataclasses import asdict, replace
    return replace(ctx, **kwargs)
