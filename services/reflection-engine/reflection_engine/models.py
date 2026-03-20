"""
Reflection Engine — Typed Policy Adjustment Proposals

The reflection-engine PROPOSES changes. It never APPLIES them.
Invariant I-10: no CandidatePolicyAdjustment may be applied without
operator_approved = True and an approval audit record.

Reference: docs/safety/formal-invariants-and-proof-obligations.md (I-10)
           docs/product/founder-operating-mode.md (Integration section)
           docs/delivery/experimental-design-and-evaluation.md (Causal Attribution)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdjustmentType:
    """Enumeration of valid adjustment types."""
    OBJECTIVE_WEIGHT    = "objective_weight"      # Change objective function weights
    ATTENTION_THRESHOLD = "attention_threshold"   # Change attention/interrupt thresholds
    CONFIDENCE_THRESHOLD = "confidence_threshold" # Change confidence gates
    MEMORY_DECAY_RATE   = "memory_decay_rate"     # Change memory class decay parameters
    COOLDOWN_DURATION   = "cooldown_duration"     # Change suppression cooldown durations
    RESURFACING_INTERVAL = "resurfacing_interval" # Change loop resurfacing frequency


@dataclass
class CandidatePolicyAdjustment:
    """
    A proposed change to system policy, emitted by the reflection-engine.

    CRITICAL INVARIANT (I-10):
    This object must NEVER be applied automatically.
    Application requires:
    1. operator_approved = True
    2. An approval audit record in the audit log
    3. No auto-application path in any service

    Implementation status: SPECIFIED
    See: docs/safety/formal-invariants-and-proof-obligations.md

    Fields:
    - id:                   Stable UUID for tracking and audit
    - adjustment_type:      Category of change (from AdjustmentType)
    - target_service:       Service that would be modified
    - target_parameter:     Specific parameter/weight to change
    - current_value:        Current value (for rollback)
    - proposed_value:       Proposed new value
    - confidence:           [0,1] Confidence that this change is beneficial
    - evidence:             Observations and metrics that led to this proposal
    - evidence_trace_ids:   Trace IDs of interactions used as evidence
    - rollback_condition:   Observable condition that triggers automatic rollback
    - rollback_threshold:   Metric threshold that defines the rollback condition
    - ablation_report_id:   Reference to ablation report if one was conducted
    - operator_approved:    MUST be False at creation; set to True only by operator
    - approval_trace_id:    Audit trace ID of the approval record
    - applied_at:           Set when (and only when) operator approves and applies
    - proposed_at:          When this proposal was created
    - expires_at:           Proposals older than this are auto-rejected
    - status:               PENDING | APPROVED | APPLIED | REJECTED | EXPIRED
    """
    id:                   str
    adjustment_type:      str
    target_service:       str
    target_parameter:     str
    current_value:        Any
    proposed_value:       Any
    confidence:           float             # [0,1] confidence this adjustment is beneficial
    evidence:             list[str]         # Human-readable observation descriptions
    evidence_trace_ids:   list[str]         # Trace IDs of supporting interactions
    rollback_condition:   str               # "if {metric} {op} {threshold} after {window}"
    rollback_threshold:   dict[str, Any]    # {"metric": str, "op": str, "value": float, "window_hours": int}
    proposed_at:          str               # ISO 8601
    expires_at:           str               # ISO 8601 — auto-rejected if not acted on

    ablation_report_id:   str | None = None  # Reference to ablation analysis
    operator_approved:    bool = False        # MUST be False at creation; I-10 enforced
    approval_trace_id:    str | None = None   # Set when approved
    applied_at:           str | None = None   # Set when applied (only after approval)
    status:               str = "PENDING"     # PENDING | APPROVED | APPLIED | REJECTED | EXPIRED
    rejection_reason:     str | None = None


@dataclass
class ReflectionInsight:
    """
    A pattern observation that may or may not lead to a CandidatePolicyAdjustment.
    Insights are always informational; adjustments are optional.

    Insight → (if confidence sufficient) → CandidatePolicyAdjustment
    CandidatePolicyAdjustment → (if operator approves) → Policy change
    """
    id:              str
    insight_type:    str   # "decision_age_drift" | "confidence_miscalibration" |
                           # "loop_abandonment_pattern" | "attention_fatigue" |
                           # "dismissal_rate_increase" | "resolution_rate_decline"
    description:     str
    evidence:        list[str]
    metric_values:   dict[str, float]    # Observed metric values
    baseline_values: dict[str, float]    # Baseline values for comparison
    delta:           dict[str, float]    # metric_values - baseline_values
    time_window:     str                 # ISO 8601 duration ("P7D" = 7 days)
    confidence:      float               # [0,1] confidence in the pattern
    produces_adjustment: bool = False    # Whether this insight triggered a proposal
    adjustment_id:   str | None = None   # If produces_adjustment: the CandidatePolicyAdjustment id
    observed_at:     str = ""


def create_adjustment(
    adjustment_type: str,
    target_service: str,
    target_parameter: str,
    current_value: Any,
    proposed_value: Any,
    confidence: float,
    evidence: list[str],
    evidence_trace_ids: list[str],
    rollback_condition: str,
    rollback_threshold: dict[str, Any],
    ablation_report_id: str | None = None,
    expiry_hours: int = 168,  # 7 days default
) -> CandidatePolicyAdjustment:
    """
    Factory function for creating CandidatePolicyAdjustment.

    Enforces:
    - operator_approved = False (cannot be True at creation)
    - status = "PENDING" (cannot be pre-approved)
    - Confidence must be in [0, 1]

    I-10 is enforced here: no CandidatePolicyAdjustment is ever created
    with operator_approved = True.
    """
    import uuid
    from datetime import timedelta

    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"Confidence must be in [0,1], got {confidence}")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=expiry_hours)

    return CandidatePolicyAdjustment(
        id=f"adj-{uuid.uuid4().hex[:12]}",
        adjustment_type=adjustment_type,
        target_service=target_service,
        target_parameter=target_parameter,
        current_value=current_value,
        proposed_value=proposed_value,
        confidence=confidence,
        evidence=evidence,
        evidence_trace_ids=evidence_trace_ids,
        rollback_condition=rollback_condition,
        rollback_threshold=rollback_threshold,
        ablation_report_id=ablation_report_id,
        proposed_at=now.isoformat(),
        expires_at=expires.isoformat(),
        operator_approved=False,  # INVARIANT I-10: never True at creation
        status="PENDING",
    )
