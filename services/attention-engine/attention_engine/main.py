"""
Attention Engine — CRK step 9

Owns: interrupt/digest/silent delivery decisions with audience routing.
Does NOT own: UI rendering, notification infrastructure, mode decisions.

V3 Upgrade: Expected-cost decision function, suppression state machine,
alert clustering, acknowledgment feedback loop, ObservationRecord logging.

Decision function (V3):
  net_value(action) = urgency_value - interruption_cost - privacy_risk
                    + predicted_ack_likelihood × ack_value
                    - time_to_decay_penalty

  decision = argmax_{INTERRUPT, QUEUE, DIGEST, SILENT} net_value(action)

Reference: docs/product/attention-decision-model.md
           docs/product/attention-memory-model.md
ADR: ADR-020 (Attention Plane)
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
import structlog

from .decision import (
    compute_attention_cost,
    make_decision,
    build_decision_rationale,
)
from .memory import (
    AttentionMemory,
    process_observation,
    update_cooldown,
)

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Attention Engine",
    description="Delivery decisions — step 9 of the CRK execution loop (V3 decision-theoretic)",
    version="0.2.0",
)

# In-memory attention state store (replace with Redis in production)
_memory_store: dict[str, AttentionMemory] = {}


def _get_memory(user_id: str, event_type_key: str) -> AttentionMemory:
    key = f"{user_id}:{event_type_key}"
    if key not in _memory_store:
        _memory_store[key] = AttentionMemory(user_id=user_id, event_type_key=event_type_key)
    return _memory_store[key]


def _save_memory(memory: AttentionMemory) -> None:
    key = f"{memory.user_id}:{memory.event_type_key}"
    _memory_store[key] = memory


class AttentionEvaluateRequest(BaseModel):
    """V3 request: includes identity_confidence and urgency_decay_rate."""
    urgency: float = 0.5                  # [0,1]
    attention_load: float = 0.0          # [0,1] from ComputerState
    identity_confidence: float = 0.8     # [0,1] from IdentityConfidence
    urgency_decay_rate: float = 0.001    # per-second decay; 0 = no decay
    user_id: str = ""
    event_type_key: str = "general"      # e.g. "irrigation.alert"
    mode: str = "PERSONAL"
    risk_class: str = "LOW"
    audience_override: list[str] = []
    elapsed_s_since_last: float = 0.0    # Seconds since last evaluation (for cooldown tick)


class ObservationFeedbackRequest(BaseModel):
    """Feed user observation back to update AttentionMemory."""
    user_id: str
    event_type_key: str
    observation_type: str  # acknowledgment | dismissal | silence | escalation | correction
    trace_id: str
    latency_ms: int = 0


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "attention-engine", "version": "0.2.0"}


@app.post("/evaluate")
async def evaluate(req: AttentionEvaluateRequest) -> dict:
    """
    POST /evaluate → AttentionDecision + AttentionCost + DecisionRationale

    V3: Expected-cost decision function with suppression state machine.
    All decisions include AttentionCost and DecisionRationale for audit logging.

    LOGGING REQUIREMENT: The response includes `attention_cost` and `decision_rationale`
    which the caller (runtime-kernel) MUST write to the audit log via POST /audit.
    """
    # Load and advance cooldown on memory
    memory = _get_memory(req.user_id, req.event_type_key)
    memory = update_cooldown(memory, req.elapsed_s_since_last)

    # Compute expected cost/value for each action
    cost = compute_attention_cost(
        urgency=req.urgency,
        mode=req.mode,
        attention_load=req.attention_load,
        identity_confidence=req.identity_confidence,
        urgency_decay_rate=req.urgency_decay_rate,
        memory=memory,
    )

    # Select best action (suppression state machine applied inside)
    decision, updated_memory = make_decision(
        cost=cost,
        memory=memory,
        risk_class=req.risk_class,
        urgency=req.urgency,
    )

    # Persist updated memory
    _save_memory(updated_memory)

    # Build rationale
    rationale = build_decision_rationale(
        decision=decision,
        cost=cost,
        memory=updated_memory,
        mode=req.mode,
        urgency=req.urgency,
        identity_confidence=req.identity_confidence,
    )

    channel = _resolve_channel(req.mode)
    audience = req.audience_override or ([req.user_id] if req.user_id else ["unknown"])
    priority = _resolve_priority(decision, req.urgency, req.risk_class)

    log.info(
        "attention_engine.decision",
        decision=decision,
        mode=req.mode,
        urgency=req.urgency,
        suppression_state=updated_memory.suppression_state,
        net_value_interrupt=round(cost.net_value("INTERRUPT"), 3),
    )

    return {
        "decision": decision,
        "channel": channel,
        "audience": audience,
        "reasoning": (
            f"net_value({decision})={cost.net_value(decision):.3f}; "
            f"suppression={updated_memory.suppression_state}"
        ),
        "delay_ms": 0,
        "priority": priority,
        # V3 scientific payload — MUST be written to audit log by caller
        "attention_cost": {
            "interruption_cost": round(cost.interruption_cost, 3),
            "urgency_value": round(cost.urgency_value, 3),
            "privacy_risk": round(cost.privacy_risk, 3),
            "predicted_ack_likelihood": round(cost.predicted_ack_likelihood, 3),
            "net_value": round(cost.net_value(decision), 3),
        },
        "decision_rationale": rationale,
        "suppression_state": updated_memory.suppression_state,
    }


@app.post("/feedback")
async def feedback(req: ObservationFeedbackRequest) -> dict:
    """
    POST /feedback — Record user observation to update AttentionMemory.

    Called by runtime-kernel after user responds to an attention decision.
    Writes ObservationRecord to audit log and updates memory for future decisions.
    """
    memory = _get_memory(req.user_id, req.event_type_key)
    updated = process_observation(req.observation_type, memory)
    _save_memory(updated)

    log.info(
        "attention_engine.feedback",
        user_id=req.user_id,
        observation_type=req.observation_type,
        new_dismissal_rate=round(updated.prior_dismissal_rate, 3),
        new_suppression_state=updated.suppression_state,
    )

    return {
        "status": "ok",
        "updated_memory": {
            "prior_dismissal_rate": round(updated.prior_dismissal_rate, 3),
            "escalation_rate": round(updated.escalation_rate, 3),
            "suppression_state": updated.suppression_state,
            "ack_count": updated.ack_count,
        },
        # ObservationRecord for caller to write to audit log
        "observation_record": {
            "trace_id": req.trace_id,
            "step": "9_attention_feedback",
            "observation_type": req.observation_type,
            "value": {"event_type_key": req.event_type_key},
            "latency_ms": req.latency_ms,
            "confidence": 1.0,
            "user_id": req.user_id,
        },
    }


@app.get("/memory/{user_id}/{event_type_key}")
async def get_memory(user_id: str, event_type_key: str) -> dict:
    """GET attention memory for a user/event type — for debugging and calibration."""
    memory = _get_memory(user_id, event_type_key)
    return {
        "user_id": memory.user_id,
        "event_type_key": memory.event_type_key,
        "prior_surfacings_count": memory.prior_surfacings_count,
        "prior_dismissal_rate": round(memory.prior_dismissal_rate, 3),
        "escalation_rate": round(memory.escalation_rate, 3),
        "ack_count": memory.ack_count,
        "cooldown_remaining_s": round(memory.cooldown_remaining_s, 1),
        "suppression_state": memory.suppression_state,
        "queue_without_ack_count": memory.queue_without_ack_count,
        "updated_at": memory.updated_at,
    }


def _resolve_channel(mode: str) -> str:
    return {
        "PERSONAL":  "VOICE",
        "FAMILY":    "WEB",
        "WORK":      "WEB",
        "SITE":      "OPS",
        "EMERGENCY": "OPS",
    }.get(mode, "WEB")


def _resolve_priority(decision: str, urgency: float, risk_class: str) -> str:
    if risk_class == "CRITICAL" or decision == "INTERRUPT" and urgency >= 0.8:
        return "CRITICAL"
    if decision == "INTERRUPT":
        return "HIGH"
    if decision == "QUEUE":
        return "NORMAL"
    return "LOW"
