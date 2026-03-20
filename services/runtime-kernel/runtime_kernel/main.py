"""
Computer Runtime Kernel — FastAPI service

The CRK coordinator. Owns request lifecycle.
Every surface entry point routes here.

Authority: docs/architecture/kernel-authority-model.md
Loop:      docs/architecture/runtime-kernel.md
ADR:       ADR-025 (CRK primary execution loop)
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import structlog

CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

from models import (
    Channel,
    ComputerState,
    ExecutionContext,
    InputEnvelope,
    Mode,
    Origin,
    ResponseEnvelope,
    RiskClass,
    Surface,
    WorkflowBinding,
    WorkflowBindingType,
    AttentionAction,
    AttentionDecision,
    AttentionPriority,
)
from runtime_kernel.loop import (
    ExecutionAuthDeniedError,
    execute_loop,
    get_audit_log,
    step1_ingest,
    step6_authorize,
    step9_attention,
    step10_render,
    _audit,
)

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Computer Runtime Kernel",
    description="Primary CRK execution loop — every surface routes here",
    version="0.1.0",
)

# ── Mode sticky map (in-memory for v1; replace with Redis in v1.1) ────────────
# Key: "user_id:surface" → Mode
_mode_map: dict[str, Mode] = {}

# ── Pydantic request models ───────────────────────────────────────────────────
from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    raw_input: str
    surface: str
    user_id: str
    session_id: str
    trace_id: str | None = None
    intent_hint: str | None = None
    mode_hint: str | None = None
    metadata: dict[str, Any] = {}


class InterruptRequest(BaseModel):
    user_id: str
    reason: str
    surface: str = "EVENT"
    trace_id: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "runtime-kernel"}


@app.post("/execute")
async def execute(req: ExecuteRequest) -> dict[str, Any]:
    """
    Main CRK entry point. ALL surfaces call this.
    Runs the full 10-step execution loop.
    Returns ResponseEnvelope serialized as JSON.
    """
    trace_id = req.trace_id or str(uuid.uuid4())

    envelope = InputEnvelope(
        raw_input=req.raw_input,
        surface=Surface(req.surface),
        user_id=req.user_id,
        session_id=req.session_id,
        trace_id=trace_id,
        intent_hint=req.intent_hint,
        mode_hint=Mode(req.mode_hint) if req.mode_hint else None,
        metadata=req.metadata,
    )

    try:
        response, ctx = await execute_loop(envelope, _mode_map)
    except ExecutionAuthDeniedError as e:
        log.warning("crk.authz_denied", trace_id=trace_id, reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        log.error("crk.loop_error", trace_id=trace_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    # Update sticky mode map from resolved context
    # Use string values (not enum repr) so GET /state keys are human-readable
    sticky_key = f"{ctx.user_id}:{ctx.surface.value}"
    _mode_map[sticky_key] = ctx.mode.value

    return _serialize_response(response)


@app.post("/interrupt")
async def interrupt(req: InterruptRequest) -> dict[str, Any]:
    """
    Emergency bypass. Skips steps 1-4.
    Jumps to step 6 with EMERGENCY risk class.
    Used by: E-stop, security alarm, operator emergency override.
    """
    trace_id = req.trace_id or str(uuid.uuid4())

    envelope = InputEnvelope(
        raw_input=f"EMERGENCY: {req.reason}",
        surface=Surface(req.surface),
        user_id=req.user_id,
        session_id=f"interrupt-{trace_id}",
        trace_id=trace_id,
    )

    ctx = step1_ingest(envelope)
    from runtime_kernel.loop import _enrich
    ctx = _enrich(
        ctx,
        intent_class="emergency.interrupt",
        risk_class=RiskClass.CRITICAL,
        origin=Origin.OPERATOR,
    )
    _audit(ctx, "interrupt_bypass", "ok",
           f"Steps 1-4 bypassed. reason={req.reason}")

    authz = await step6_authorize(ctx)
    if not authz.allowed:
        raise HTTPException(status_code=403, detail=f"Emergency interrupt denied: {authz.reason}")

    attention = await step9_attention(ctx)
    response = step10_render(ctx, None, [], attention)
    return _serialize_response(response)


@app.get("/state")
async def state() -> dict[str, Any]:
    """
    Returns Computer's current state of mind.
    Mode map, active workflows, attention load, system health.
    """
    computer_state = ComputerState(
        mode_by_surface=dict(_mode_map),
        active_workflow_ids=[],   # Populated by workflow-runtime when live
        pending_commitments=[],
        attention_load=0.0,
        system_health_flags=[],
        active_emergency=False,
    )
    return {
        "mode_by_surface": computer_state.mode_by_surface,
        "active_workflow_ids": computer_state.active_workflow_ids,
        "pending_commitments": computer_state.pending_commitments,
        "attention_load": computer_state.attention_load,
        "system_health_flags": computer_state.system_health_flags,
        "active_emergency": computer_state.active_emergency,
    }


@app.get("/audit")
async def audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent step audit records for debugging."""
    records = get_audit_log()[-limit:]
    return [
        {
            "request_id": r.request_id,
            "trace_id": r.trace_id,
            "step": r.step,
            "status": r.status,
            "detail": r.detail,
            "duration_ms": r.duration_ms,
        }
        for r in records
    ]


@app.get("/audit/{trace_id}")
async def audit_by_trace(trace_id: str) -> list[dict[str, Any]]:
    """Return all audit steps for a specific trace_id."""
    records = [r for r in get_audit_log() if r.trace_id == trace_id]
    return [
        {
            "step": r.step,
            "status": r.status,
            "detail": r.detail,
            "duration_ms": r.duration_ms,
        }
        for r in records
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_response(resp: ResponseEnvelope) -> dict[str, Any]:
    return {
        "content": resp.content,
        "channel": resp.channel,
        "trace_id": resp.trace_id,
        "proposed_jobs": resp.proposed_jobs,
        "attention_decision": {
            "decision": resp.attention_decision.decision,
            "channel": resp.attention_decision.channel,
            "audience": resp.attention_decision.audience,
            "reasoning": resp.attention_decision.reasoning,
            "delay_ms": resp.attention_decision.delay_ms,
            "priority": resp.attention_decision.priority,
        },
        "workflow_binding": {
            "workflow_id": resp.workflow_binding.workflow_id,
            "type": resp.workflow_binding.type,
            "temporal_task_queue": resp.workflow_binding.temporal_task_queue,
            "job_id": resp.workflow_binding.job_id,
        } if resp.workflow_binding else None,
    }
