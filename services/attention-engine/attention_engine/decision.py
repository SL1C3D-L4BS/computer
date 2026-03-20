"""
Attention Decision — Expected-cost/value decision function.

Implements the decision-theoretic attention model from:
docs/product/attention-decision-model.md

All terms are normalized to [0,1]. net_value is clipped to [-1, 1].
Decision = argmax_{INTERRUPT, QUEUE, DIGEST, SILENT} net_value(action).

Suppression state machine is enforced AFTER net_value computation:
- SUPPRESSED state blocks INTERRUPT (unless CRITICAL/FORCE)
- ESCALATION_PENDING forces INTERRUPT on next event
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .memory import AttentionMemory, record_interrupt_fired, record_queued

# ── Constants ─────────────────────────────────────────────────────────────────

COOLDOWN_BY_MODE: dict[str, float] = {
    "PERSONAL":  120.0,
    "FAMILY":    180.0,
    "WORK":      300.0,
    "SITE":       60.0,
    "EMERGENCY":   0.0,
}

MODE_URGENCY_WEIGHT: dict[str, float] = {
    "PERSONAL":  0.8,
    "FAMILY":    0.9,
    "WORK":      0.7,
    "SITE":      1.0,
    "EMERGENCY": 1.5,
}

PRIVACY_RISK_BASE: dict[str, float] = {
    "PERSONAL":  0.10,
    "FAMILY":    0.30,
    "WORK":      0.20,
    "SITE":      0.10,
    "EMERGENCY": 0.00,
}

# Effective delay in seconds for each action (used for decay penalty)
EFFECTIVE_DELAY_S: dict[str, float] = {
    "INTERRUPT": 0,
    "QUEUE":     300,    # ~5 min
    "DIGEST":    3600,   # ~1 hr
    "SILENT":    86400,  # ~24 hr
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Core decision computation ─────────────────────────────────────────────────

@dataclass
class AttentionCostResult:
    interruption_cost:        float
    urgency_value:            float
    privacy_risk:             float
    predicted_ack_likelihood: float
    time_to_decay_penalty_interrupt: float
    time_to_decay_penalty_queue:     float
    time_to_decay_penalty_digest:    float
    time_to_decay_penalty_silent:    float

    def net_value(self, action: str) -> float:
        delay_penalty = {
            "INTERRUPT": self.time_to_decay_penalty_interrupt,
            "QUEUE":     self.time_to_decay_penalty_queue,
            "DIGEST":    self.time_to_decay_penalty_digest,
            "SILENT":    self.time_to_decay_penalty_silent,
        }[action]

        ack_value = self.urgency_value * 0.8 + 0.2  # floor of 0.2
        raw = (
            self.urgency_value
            - self.interruption_cost
            - self.privacy_risk
            + self.predicted_ack_likelihood * ack_value
            - delay_penalty
        )
        return _clamp(raw, -1.0, 1.0)


def compute_attention_cost(
    urgency: float,
    mode: str,
    attention_load: float,
    identity_confidence: float,
    urgency_decay_rate: float,
    memory: AttentionMemory,
) -> AttentionCostResult:
    """
    Computes the AttentionCostResult for each potential action.
    All inputs normalized; all outputs normalized.
    Reference: docs/product/attention-decision-model.md
    """
    # urgency_value: mode-weighted urgency
    urgency_value = _clamp(urgency * MODE_URGENCY_WEIGHT.get(mode, 1.0))

    # interruption_cost: attention_load × 0.7 + cooldown_factor × 0.3
    max_cooldown = max(COOLDOWN_BY_MODE.values())
    cooldown_factor = _clamp(memory.cooldown_remaining_s / max(max_cooldown, 1))
    interruption_cost = _clamp(attention_load * 0.7 + cooldown_factor * 0.3)

    # privacy_risk: mode base + identity uncertainty premium
    base_risk = PRIVACY_RISK_BASE.get(mode, 0.2)
    identity_uncertainty = (1.0 - identity_confidence) * 0.5
    privacy_risk = _clamp(base_risk + identity_uncertainty)

    # predicted_ack_likelihood from memory
    ack_p = memory.predicted_ack_likelihood(mode)

    # time_to_decay_penalty per action
    def decay_penalty(delay_s: float) -> float:
        return _clamp(1.0 - math.exp(-urgency_decay_rate * delay_s))

    return AttentionCostResult(
        interruption_cost=interruption_cost,
        urgency_value=urgency_value,
        privacy_risk=privacy_risk,
        predicted_ack_likelihood=ack_p,
        time_to_decay_penalty_interrupt=decay_penalty(EFFECTIVE_DELAY_S["INTERRUPT"]),
        time_to_decay_penalty_queue=decay_penalty(EFFECTIVE_DELAY_S["QUEUE"]),
        time_to_decay_penalty_digest=decay_penalty(EFFECTIVE_DELAY_S["DIGEST"]),
        time_to_decay_penalty_silent=decay_penalty(EFFECTIVE_DELAY_S["SILENT"]),
    )


def make_decision(
    cost: AttentionCostResult,
    memory: AttentionMemory,
    risk_class: str = "LOW",
    urgency: float = 0.5,
) -> tuple[str, AttentionMemory]:
    """
    Select the action with maximum net_value, then apply suppression state machine.
    Returns: (decision: str, updated_memory: AttentionMemory)
    """
    # Suppression state machine takes precedence over net_value in some cases
    if memory.suppression_state == "ESCALATION_PENDING":
        # Force INTERRUPT on next event of same type
        updated = record_interrupt_fired(memory, COOLDOWN_BY_MODE.get(memory.event_type_key, 120))
        return "INTERRUPT", updated

    # CRITICAL or HIGH+urgent bypass SUPPRESSED state
    if memory.suppression_state == "SUPPRESSED":
        if risk_class == "CRITICAL" or (risk_class == "HIGH" and urgency > 0.85):
            updated = memory  # Don't reset cooldown on FORCE_INTERRUPT
            return "INTERRUPT", updated

    # Normal decision: argmax net_value
    actions = ["INTERRUPT", "QUEUE", "DIGEST", "SILENT"]
    best_action = max(actions, key=lambda a: cost.net_value(a))

    # If ALL actions have negative net_value, delivering is net-negative regardless of when.
    # Downgrade: don't INTERRUPT when the best case is still a net loss.
    # This prevents INTERRUPT "winning" just because its delay penalty is 0.
    if cost.net_value(best_action) < 0:
        if best_action == "INTERRUPT":
            best_action = "QUEUE"   # Defer rather than intrude when all outcomes are negative

    # Block INTERRUPT if suppressed (not force)
    if best_action == "INTERRUPT" and memory.suppression_state == "SUPPRESSED":
        best_action = "QUEUE"

    # Update memory based on decision
    if best_action == "INTERRUPT":
        cooldown_s = COOLDOWN_BY_MODE.get(
            memory.event_type_key.split(".")[0].upper() if "." in memory.event_type_key
            else "PERSONAL", 120
        )
        updated_memory = record_interrupt_fired(memory, cooldown_s)
    elif best_action == "QUEUE":
        updated_memory = record_queued(memory)
    else:
        from dataclasses import replace
        updated_memory = replace(memory, updated_at=now_iso())

    return best_action, updated_memory


def build_decision_rationale(
    decision: str,
    cost: AttentionCostResult,
    memory: AttentionMemory,
    mode: str,
    urgency: float,
    identity_confidence: float,
    constraints_checked: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a DecisionRationale-compatible dict for the audit log.
    All decisions at step 9 must produce one of these.
    Reference: docs/product/attention-decision-model.md (DecisionRationale at Step 9)
    """
    return {
        "decision": decision,
        "inputs": {
            "urgency": urgency,
            "mode": mode,
            "identity_confidence": identity_confidence,
            "attention_load_proxy": cost.interruption_cost,
            "prior_dismissal_rate": memory.prior_dismissal_rate,
            "cooldown_remaining_s": memory.cooldown_remaining_s,
            "suppression_state": memory.suppression_state,
        },
        "confidence": {
            "value": identity_confidence,
            "type": "identity",
            "source": "attention-engine",
            "decay_rate_per_s": 0.01,
            "computed_at": now_iso(),
        },
        "objective_weights": {
            "urgency_value": 1.0,
            "interruption_cost": -1.0,
            "privacy_risk": -1.0,
            "predicted_ack_likelihood": cost.predicted_ack_likelihood,
        },
        "constraints_checked": constraints_checked or ["HC-01"],
        "hard_constraints_violated": [],
        "alternatives_considered": ["INTERRUPT", "QUEUE", "DIGEST", "SILENT"],
        "net_values": {
            "INTERRUPT": cost.net_value("INTERRUPT"),
            "QUEUE":     cost.net_value("QUEUE"),
            "DIGEST":    cost.net_value("DIGEST"),
            "SILENT":    cost.net_value("SILENT"),
        },
        "decided_at": now_iso(),
    }
