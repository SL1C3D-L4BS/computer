"""
Attention Memory — Per-user, per-event-type state for the suppression state machine.

Stores: prior dismissal rate, escalation rate, cooldown state, surfacing history.
Powers: predicted_ack_likelihood, suppression state machine, escalation detection.

Reference: docs/product/attention-memory-model.md
           docs/product/attention-decision-model.md
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone


ROLLING_ALPHA = 0.1   # EMA weight for observation updates


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ema(current: float, new_value: float, alpha: float = ROLLING_ALPHA) -> float:
    """Exponential moving average update."""
    return (1 - alpha) * current + alpha * new_value


@dataclass
class AttentionMemory:
    """
    Per-user, per-event-type attention state.
    Persisted in Redis with TTL=7 days.
    Key: attn:memory:{user_id}:{event_type_key}

    All float fields: [0,1] per measurement-and-scaling-model.md
    """
    user_id:                str
    event_type_key:         str
    prior_surfacings_count: int   = 0
    prior_dismissal_rate:   float = 0.0   # [0,1] EMA of dismissals
    dismissal_count:        int   = 0
    escalation_rate:        float = 0.0   # [0,1] EMA of escalations
    ack_count:              int   = 0
    last_surfaced_at:       float = 0.0   # Epoch seconds
    cooldown_remaining_s:   float = 0.0   # Remaining suppression seconds
    suppression_state:      str   = "NORMAL"  # NORMAL | SUPPRESSED | ESCALATION_PENDING
    queue_without_ack_count: int  = 0     # Times QUEUEd without ack (for escalation trigger)
    updated_at:             str   = ""

    def current_effective_dismissal_rate(self) -> float:
        """Effective dismissal rate; recent history weighted by EMA."""
        return self.prior_dismissal_rate

    def predicted_ack_likelihood(self, mode: str) -> float:
        """
        Estimate probability user acknowledges this event type.
        Based on: mode base rate + history modifier.
        Range: [0.05, 0.95] — never fully certain in either direction.
        """
        BASE_ACK_RATE = {
            "PERSONAL": 0.60,
            "FAMILY": 0.50,
            "WORK": 0.40,
            "SITE": 0.55,
            "EMERGENCY": 0.85,
        }
        base = BASE_ACK_RATE.get(mode, 0.50)

        # Modifiers from history: [-0.4, +0.4]
        dismissal_penalty = -self.prior_dismissal_rate * 0.4
        escalation_bonus  = self.escalation_rate * 0.3
        surfacing_penalty = min(0.1, self.prior_surfacings_count * 0.01)  # cap penalty

        modifier = dismissal_penalty + escalation_bonus - surfacing_penalty
        return max(0.05, min(0.95, base + modifier))


def update_cooldown(memory: AttentionMemory, elapsed_s: float) -> AttentionMemory:
    """Advance cooldown timer; transition to NORMAL when expired."""
    if memory.suppression_state != "SUPPRESSED":
        return memory

    new_cooldown = max(0.0, memory.cooldown_remaining_s - elapsed_s)
    new_state = "NORMAL" if new_cooldown <= 0.0 else "SUPPRESSED"
    return replace(
        memory,
        cooldown_remaining_s=new_cooldown,
        suppression_state=new_state,
        updated_at=now_iso(),
    )


def process_observation(obs_type: str, memory: AttentionMemory) -> AttentionMemory:
    """
    Update memory from a user observation (ack / dismissal / silence / escalation / correction).
    Returns an updated copy; does not mutate in place.
    Reference: docs/product/attention-memory-model.md (Observation Feedback Loop)
    """
    updated = replace(memory, updated_at=now_iso())

    if obs_type == "acknowledgment":
        updated = replace(
            updated,
            ack_count=memory.ack_count + 1,
            prior_dismissal_rate=ema(memory.prior_dismissal_rate, 0.0),
            queue_without_ack_count=0,   # reset escalation counter
        )
    elif obs_type == "dismissal":
        updated = replace(
            updated,
            dismissal_count=memory.dismissal_count + 1,
            prior_dismissal_rate=ema(memory.prior_dismissal_rate, 1.0),
        )
    elif obs_type == "silence":
        updated = replace(
            updated,
            prior_dismissal_rate=ema(memory.prior_dismissal_rate, 0.5),
        )
    elif obs_type == "escalation":
        updated = replace(
            updated,
            escalation_rate=ema(memory.escalation_rate, 1.0),
            suppression_state="NORMAL",   # escalation resets suppression
            cooldown_remaining_s=0.0,
        )
    elif obs_type == "correction":
        # Strong negative signal — user actively corrected the system
        updated = replace(
            updated,
            prior_dismissal_rate=ema(memory.prior_dismissal_rate, 1.0, ROLLING_ALPHA * 3),
        )

    return updated


def record_interrupt_fired(memory: AttentionMemory, cooldown_s: float) -> AttentionMemory:
    """Call after an INTERRUPT decision is emitted; sets suppression."""
    return replace(
        memory,
        prior_surfacings_count=memory.prior_surfacings_count + 1,
        last_surfaced_at=_now_epoch(),
        suppression_state="SUPPRESSED",
        cooldown_remaining_s=cooldown_s,
        queue_without_ack_count=0,
        updated_at=now_iso(),
    )


def record_queued(memory: AttentionMemory) -> AttentionMemory:
    """Call after a QUEUE decision; may trigger escalation if repeated."""
    new_count = memory.queue_without_ack_count + 1
    new_state = "ESCALATION_PENDING" if new_count >= 3 else memory.suppression_state
    return replace(
        memory,
        prior_surfacings_count=memory.prior_surfacings_count + 1,
        last_surfaced_at=_now_epoch(),
        queue_without_ack_count=new_count,
        suppression_state=new_state,
        updated_at=now_iso(),
    )


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()
