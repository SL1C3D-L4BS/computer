"""
Reflection Engine — Pattern analysis and policy adjustment proposals.

What it does:
- Analyzes audit trail patterns: decision age drift, confidence miscalibration,
  loop abandonment patterns, attention fatigue, dismissal rate changes
- Emits typed CandidatePolicyAdjustment objects when evidence is sufficient
- Requires operator approval before any adjustment is applied (invariant I-10)
- Records all proposals to the audit log for transparency

What it NEVER does:
- Auto-apply any policy change
- Modify service configuration directly
- Change objective weights without approval
- Access or modify memory content
- Create ExecutionContext objects (not a request handler)

Invariant I-10: CandidatePolicyAdjustment.operator_approved = False at all times
until an operator explicitly approves via POST /proposals/{id}/approve.

Reference: docs/safety/formal-invariants-and-proof-obligations.md (I-10)
           docs/delivery/experimental-design-and-evaluation.md
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

from .models import (
    AdjustmentType,
    CandidatePolicyAdjustment,
    ReflectionInsight,
    create_adjustment,
)

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Reflection Engine",
    description=(
        "Pattern analysis and typed policy adjustment proposals. "
        "NEVER auto-applies changes. All proposals require operator approval (I-10)."
    ),
    version="0.1.0",
)

# In-memory proposal and insight stores (replace with PostgreSQL in production)
_proposals: dict[str, CandidatePolicyAdjustment] = {}
_insights: dict[str, ReflectionInsight] = {}


class AnalysisInput(BaseModel):
    """Input for a reflection analysis request."""
    analysis_type: str     # "decision_age" | "attention_fatigue" | "confidence_calibration" | "loop_abandonment"
    time_window_hours: int = 168   # 7 days default
    metric_data: dict[str, Any] = {}
    trace_ids: list[str] = []
    baseline_data: dict[str, Any] = {}


class ApprovalRequest(BaseModel):
    """Operator approval for a pending proposal."""
    operator_id: str
    approval_trace_id: str   # Must come from an authenticated operator session
    notes: str = ""


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "reflection-engine",
        "invariant_I10": "enforced",
        "pending_proposals": str(len([p for p in _proposals.values() if p.status == "PENDING"])),
    }


@app.post("/analyze")
async def analyze(req: AnalysisInput) -> dict:
    """
    POST /analyze — Run pattern analysis on provided metric data.

    Returns: ReflectionInsight and optionally a CandidatePolicyAdjustment
    if evidence is sufficient (confidence ≥ 0.60).

    CRITICAL: This endpoint NEVER applies any change.
    """
    insight, proposal = _run_analysis(req)

    _insights[insight.id] = insight
    result: dict[str, Any] = {
        "insight_id": insight.id,
        "insight_type": insight.insight_type,
        "description": insight.description,
        "confidence": insight.confidence,
        "metric_deltas": insight.delta,
        "produces_adjustment": insight.produces_adjustment,
    }

    if proposal:
        _proposals[proposal.id] = proposal
        log.info(
            "reflection_engine.proposal_created",
            proposal_id=proposal.id,
            adjustment_type=proposal.adjustment_type,
            target=f"{proposal.target_service}.{proposal.target_parameter}",
            confidence=proposal.confidence,
            operator_approved=proposal.operator_approved,  # Always False
        )
        result["proposal"] = {
            "id": proposal.id,
            "adjustment_type": proposal.adjustment_type,
            "target_service": proposal.target_service,
            "target_parameter": proposal.target_parameter,
            "current_value": proposal.current_value,
            "proposed_value": proposal.proposed_value,
            "confidence": proposal.confidence,
            "rollback_condition": proposal.rollback_condition,
            "operator_approved": proposal.operator_approved,   # Always False
            "status": proposal.status,
            "expires_at": proposal.expires_at,
        }

    return result


@app.get("/proposals")
async def list_proposals(status: str | None = None) -> dict:
    """GET /proposals — List all policy adjustment proposals."""
    proposals = list(_proposals.values())
    if status:
        proposals = [p for p in proposals if p.status == status]
    return {
        "proposals": [
            {
                "id": p.id,
                "adjustment_type": p.adjustment_type,
                "target_service": p.target_service,
                "target_parameter": p.target_parameter,
                "confidence": p.confidence,
                "operator_approved": p.operator_approved,
                "status": p.status,
                "proposed_at": p.proposed_at,
                "expires_at": p.expires_at,
            }
            for p in proposals
        ],
        "count": len(proposals),
    }


@app.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str) -> dict:
    """GET /proposals/{id} — Get full proposal details."""
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    return {
        "id": proposal.id,
        "adjustment_type": proposal.adjustment_type,
        "target_service": proposal.target_service,
        "target_parameter": proposal.target_parameter,
        "current_value": proposal.current_value,
        "proposed_value": proposal.proposed_value,
        "confidence": proposal.confidence,
        "evidence": proposal.evidence,
        "evidence_trace_ids": proposal.evidence_trace_ids,
        "rollback_condition": proposal.rollback_condition,
        "rollback_threshold": proposal.rollback_threshold,
        "operator_approved": proposal.operator_approved,
        "approval_trace_id": proposal.approval_trace_id,
        "applied_at": proposal.applied_at,
        "status": proposal.status,
        "proposed_at": proposal.proposed_at,
        "expires_at": proposal.expires_at,
    }


@app.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, req: ApprovalRequest) -> dict:
    """
    POST /proposals/{id}/approve — Operator approves a proposal.

    This sets operator_approved = True and status = APPROVED.
    The proposal is NOT yet applied — it must be explicitly applied
    via POST /proposals/{id}/apply after review.

    This is the I-10 approval gate.
    """
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    if proposal.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal is {proposal.status}, not PENDING. Cannot approve.",
        )

    proposal.operator_approved = True
    proposal.approval_trace_id = req.approval_trace_id
    proposal.status = "APPROVED"

    log.info(
        "reflection_engine.proposal_approved",
        proposal_id=proposal_id,
        operator_id=req.operator_id,
        approval_trace_id=req.approval_trace_id,
    )

    return {
        "status": "approved",
        "proposal_id": proposal_id,
        "operator_approved": True,
        "next_step": "POST /proposals/{id}/apply to apply the change",
    }


@app.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, reason: str = "") -> dict:
    """POST /proposals/{id}/reject — Operator rejects a proposal."""
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    proposal.status = "REJECTED"
    proposal.rejection_reason = reason

    log.info("reflection_engine.proposal_rejected", proposal_id=proposal_id, reason=reason)
    return {"status": "rejected", "proposal_id": proposal_id}


@app.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: str) -> dict:
    """
    POST /proposals/{id}/apply — Apply an approved proposal.

    INVARIANT I-10: This endpoint requires operator_approved = True.
    If not approved, returns 403.

    Currently a stub: logs the intended change but does not actually modify
    any service configuration. Real implementation would call the target
    service's configuration API with the proposed_value.
    """
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    # I-10 enforcement: hard gate
    if not proposal.operator_approved:
        log.error(
            "reflection_engine.I10_violation_attempt",
            proposal_id=proposal_id,
            invariant="I-10",
            message="Apply attempted without operator approval",
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "invariant_I10_violation",
                "message": "Cannot apply proposal without operator_approved = True",
                "invariant": "I-10",
                "proposal_id": proposal_id,
            },
        )

    if proposal.status != "APPROVED":
        raise HTTPException(
            status_code=400,
            detail=f"Proposal status is {proposal.status}, expected APPROVED",
        )

    from datetime import datetime, timezone
    proposal.applied_at = datetime.now(timezone.utc).isoformat()
    proposal.status = "APPLIED"

    log.info(
        "reflection_engine.proposal_applied",
        proposal_id=proposal_id,
        target=f"{proposal.target_service}.{proposal.target_parameter}",
        current_value=proposal.current_value,
        proposed_value=proposal.proposed_value,
        approval_trace_id=proposal.approval_trace_id,
    )

    # STUB: real implementation would call target service configuration API
    return {
        "status": "applied",
        "proposal_id": proposal_id,
        "target_service": proposal.target_service,
        "target_parameter": proposal.target_parameter,
        "applied_value": proposal.proposed_value,
        "applied_at": proposal.applied_at,
        "rollback_condition": proposal.rollback_condition,
        "stub": True,  # Remove when real config API is wired
    }


# ── Analysis Logic ─────────────────────────────────────────────────────────────

def _run_analysis(
    req: AnalysisInput,
) -> tuple[ReflectionInsight, CandidatePolicyAdjustment | None]:
    """
    Run pattern analysis and return insight + optional proposal.
    Real implementation queries the audit log database.
    This stub demonstrates the output contract.
    """
    from datetime import datetime, timezone

    insight_id = f"ins-{uuid.uuid4().hex[:12]}"
    metric_data = req.metric_data or {}
    baseline_data = req.baseline_data or {}
    delta = {k: metric_data.get(k, 0) - baseline_data.get(k, 0) for k in metric_data}

    analysis_map = {
        "decision_age":            _analyze_decision_age,
        "attention_fatigue":       _analyze_attention_fatigue,
        "confidence_calibration":  _analyze_confidence_calibration,
        "loop_abandonment":        _analyze_loop_abandonment,
    }

    analyzer = analysis_map.get(req.analysis_type, _analyze_generic)
    description, confidence, insight_type = analyzer(metric_data, baseline_data, delta)

    insight = ReflectionInsight(
        id=insight_id,
        insight_type=insight_type,
        description=description,
        evidence=list(metric_data.keys()),
        metric_values=metric_data,
        baseline_values=baseline_data,
        delta=delta,
        time_window=f"PT{req.time_window_hours}H",
        confidence=confidence,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )

    proposal = None
    if confidence >= 0.60:
        proposal = _build_proposal_from_insight(insight, req)
        if proposal:
            insight.produces_adjustment = True
            insight.adjustment_id = proposal.id

    return insight, proposal


def _analyze_decision_age(
    metric_data: dict, baseline_data: dict, delta: dict
) -> tuple[str, float, str]:
    mean_age = metric_data.get("mean_decision_age_hours", 0)
    baseline_age = baseline_data.get("mean_decision_age_hours", 0)
    drift = delta.get("mean_decision_age_hours", 0)

    if drift > 12:
        confidence = min(0.85, 0.60 + (drift / 24) * 0.25)
        return (
            f"Decision age increased by {drift:.1f}h (baseline {baseline_age:.1f}h → current {mean_age:.1f}h). "
            "Open loop resurfacing threshold may be too high.",
            confidence,
            "decision_age_drift",
        )
    return ("Decision age within normal range.", 0.20, "decision_age_ok")


def _analyze_attention_fatigue(
    metric_data: dict, baseline_data: dict, delta: dict
) -> tuple[str, float, str]:
    dismissal_rate = metric_data.get("dismissal_rate", 0)
    baseline_rate = baseline_data.get("dismissal_rate", 0)
    drift = delta.get("dismissal_rate", 0)

    if dismissal_rate > 0.20 and drift > 0.05:
        confidence = min(0.80, 0.60 + drift * 2.0)
        return (
            f"Dismissal rate {dismissal_rate:.2f} exceeds 0.20 threshold "
            f"(increased by {drift:.2f} from baseline). Cooldown duration may need increase.",
            confidence,
            "attention_fatigue",
        )
    return ("Dismissal rate within acceptable range.", 0.15, "attention_ok")


def _analyze_confidence_calibration(
    metric_data: dict, baseline_data: dict, delta: dict
) -> tuple[str, float, str]:
    brier_score = metric_data.get("brier_score", 0)
    if brier_score > 0.25:
        confidence = min(0.75, 0.60 + (brier_score - 0.25) * 1.5)
        return (
            f"Brier score {brier_score:.3f} exceeds calibration target 0.25. "
            "Confidence model may need recalibration.",
            confidence,
            "confidence_miscalibration",
        )
    return ("Confidence calibration within target.", 0.10, "confidence_ok")


def _analyze_loop_abandonment(
    metric_data: dict, baseline_data: dict, delta: dict
) -> tuple[str, float, str]:
    abandonment_rate = metric_data.get("abandonment_rate", 0)
    if abandonment_rate > 0.15:
        confidence = min(0.78, 0.60 + (abandonment_rate - 0.15) * 2.0)
        return (
            f"Loop abandonment rate {abandonment_rate:.2f} exceeds 0.10 target. "
            "Loop priority scoring or half-life values may need adjustment.",
            confidence,
            "loop_abandonment_pattern",
        )
    return ("Loop abandonment rate within target.", 0.10, "loop_abandonment_ok")


def _analyze_generic(
    metric_data: dict, baseline_data: dict, delta: dict
) -> tuple[str, float, str]:
    return ("Generic analysis — no specific pattern detected.", 0.10, "generic")


def _build_proposal_from_insight(
    insight: ReflectionInsight,
    req: AnalysisInput,
) -> CandidatePolicyAdjustment | None:
    """Build a proposal from an insight, if applicable."""

    PROPOSAL_MAP = {
        "decision_age_drift": {
            "adjustment_type": AdjustmentType.RESURFACING_INTERVAL,
            "target_service": "runtime-kernel",
            "target_parameter": "continuity_processor.resurfacing_threshold",
            "current_value": 0.15,
            "proposed_value": 0.12,
            "rollback_condition": "if mean_decision_age_hours > current + 24 after 48h",
            "rollback_threshold": {"metric": "mean_decision_age_hours", "op": ">", "value": 0.0, "window_hours": 48},
        },
        "attention_fatigue": {
            "adjustment_type": AdjustmentType.COOLDOWN_DURATION,
            "target_service": "attention-engine",
            "target_parameter": "COOLDOWN_BY_MODE.PERSONAL",
            "current_value": 120,
            "proposed_value": 180,
            "rollback_condition": "if dismissal_rate > 0.25 after 48h or missed_critical > 0",
            "rollback_threshold": {"metric": "dismissal_rate", "op": ">", "value": 0.25, "window_hours": 48},
        },
        "confidence_miscalibration": {
            "adjustment_type": AdjustmentType.ATTENTION_THRESHOLD,
            "target_service": "attention-engine",
            "target_parameter": "BASE_ACK_RATE.PERSONAL",
            "current_value": 0.60,
            "proposed_value": 0.55,
            "rollback_condition": "if brier_score > 0.30 after 7d eval run",
            "rollback_threshold": {"metric": "brier_score", "op": ">", "value": 0.30, "window_hours": 168},
        },
        "loop_abandonment_pattern": {
            "adjustment_type": AdjustmentType.MEMORY_DECAY_RATE,
            "target_service": "runtime-kernel",
            "target_parameter": "loop_decay_defaults.household_tasks.half_life_hours",
            "current_value": 48.0,
            "proposed_value": 72.0,
            "rollback_condition": "if abandonment_rate > 0.20 after 14d",
            "rollback_threshold": {"metric": "abandonment_rate", "op": ">", "value": 0.20, "window_hours": 336},
        },
    }

    config = PROPOSAL_MAP.get(insight.insight_type)
    if not config:
        return None

    return create_adjustment(
        adjustment_type=config["adjustment_type"],
        target_service=config["target_service"],
        target_parameter=config["target_parameter"],
        current_value=config["current_value"],
        proposed_value=config["proposed_value"],
        confidence=insight.confidence,
        evidence=insight.evidence,
        evidence_trace_ids=req.trace_ids,
        rollback_condition=config["rollback_condition"],
        rollback_threshold=config["rollback_threshold"],
    )
