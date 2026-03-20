"""
Hydroponics bay state machine.

States:
  IDLE → MONITORING → DOSING_NUTRIENTS | ADJUSTING_PH | CIRCULATING → MONITORING
  Any state → SAFE_HOLD (E-stop or fault)

Safety rules:
  - pH and EC dosing are sequential, never concurrent (risk of precipitation)
  - Minimum interval between dosing events enforced
  - All dosing goes through orchestrator job proposal
  - Max dose volumes enforced at policy level
"""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class BayState(str, Enum):
    IDLE = "IDLE"
    MONITORING = "MONITORING"
    DOSING_NUTRIENTS = "DOSING_NUTRIENTS"
    ADJUSTING_PH = "ADJUSTING_PH"
    CIRCULATING = "CIRCULATING"
    SAFE_HOLD = "SAFE_HOLD"


ALLOWED_TRANSITIONS: dict[BayState, set[BayState]] = {
    BayState.IDLE: {BayState.MONITORING, BayState.SAFE_HOLD},
    BayState.MONITORING: {
        BayState.DOSING_NUTRIENTS,
        BayState.ADJUSTING_PH,
        BayState.CIRCULATING,
        BayState.IDLE,
        BayState.SAFE_HOLD,
    },
    BayState.DOSING_NUTRIENTS: {BayState.MONITORING, BayState.SAFE_HOLD},
    BayState.ADJUSTING_PH: {BayState.MONITORING, BayState.SAFE_HOLD},
    BayState.CIRCULATING: {BayState.MONITORING, BayState.SAFE_HOLD},
    BayState.SAFE_HOLD: {BayState.IDLE},
}

# Minimum seconds between dosing events (safety: allow chemistry to mix)
MIN_DOSE_INTERVAL_SECONDS = 300  # 5 minutes


class BayStateMachine:
    def __init__(self, bay_id: str):
        self.bay_id = bay_id
        self.state = BayState.IDLE
        self.state_entered_at = datetime.utcnow()
        self.last_reading: dict[str, Any] = {}
        self.last_dose_at: datetime | None = None
        self.last_ph_adjust_at: datetime | None = None
        self.pending_job_id: str | None = None
        self._log = logger.bind(bay_id=bay_id)

    def transition(self, target: BayState, *, reason: str | None = None) -> BayState:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Bay {self.bay_id}: cannot transition {self.state} → {target}")
        prev = self.state
        self.state = target
        self.state_entered_at = datetime.utcnow()
        self._log.info("bay_state_transition", from_state=prev, to_state=target, reason=reason)
        return target

    def e_stop(self, reason: str = "E-stop") -> None:
        prev = self.state
        self.state = BayState.SAFE_HOLD
        self.state_entered_at = datetime.utcnow()
        self.pending_job_id = None
        self._log.warning("bay_e_stop", from_state=prev, reason=reason)

    def clear_safe_hold(self) -> None:
        if self.state != BayState.SAFE_HOLD:
            raise ValueError(f"Bay {self.bay_id} is not in SAFE_HOLD")
        self.transition(BayState.IDLE, reason="Operator cleared safe hold")

    def update_reading(self, readings: dict[str, Any]) -> None:
        self.last_reading = {**readings, "received_at": datetime.utcnow().isoformat()}

    def can_dose(self) -> tuple[bool, str | None]:
        """Check if dosing interval has elapsed."""
        if self.last_dose_at is None:
            return True, None
        elapsed = (datetime.utcnow() - self.last_dose_at).total_seconds()
        if elapsed < MIN_DOSE_INTERVAL_SECONDS:
            remaining = int(MIN_DOSE_INTERVAL_SECONDS - elapsed)
            return False, f"Min dose interval not elapsed ({remaining}s remaining)"
        return True, None

    def can_adjust_ph(self) -> tuple[bool, str | None]:
        """Check if pH adjustment interval has elapsed."""
        if self.last_ph_adjust_at is None:
            return True, None
        elapsed = (datetime.utcnow() - self.last_ph_adjust_at).total_seconds()
        if elapsed < MIN_DOSE_INTERVAL_SECONDS:
            remaining = int(MIN_DOSE_INTERVAL_SECONDS - elapsed)
            return False, f"Min pH adjust interval not elapsed ({remaining}s remaining)"
        return True, None

    def evaluate_nutrient_need(
        self,
        target_ec_ms: float = 1.6,
        tolerance: float = 0.2,
    ) -> bool:
        """Returns True if EC is below target — nutrient dosing may be needed."""
        ec = self.last_reading.get("ec_ms")
        if ec is None:
            return False
        return float(ec) < (target_ec_ms - tolerance)

    def evaluate_ph_need(
        self,
        target_ph: float = 6.0,
        tolerance: float = 0.3,
    ) -> dict[str, Any] | None:
        """
        Returns dosing direction or None.
        Returns {'direction': 'up'|'down', 'current_ph': ..., 'target_ph': ...}
        """
        ph = self.last_reading.get("ph")
        if ph is None:
            return None
        ph = float(ph)
        if ph < (target_ph - tolerance):
            return {"direction": "up", "current_ph": ph, "target_ph": target_ph}
        if ph > (target_ph + tolerance):
            return {"direction": "down", "current_ph": ph, "target_ph": target_ph}
        return None

    def record_dose(self) -> None:
        self.last_dose_at = datetime.utcnow()

    def record_ph_adjust(self) -> None:
        self.last_ph_adjust_at = datetime.utcnow()

    def status(self) -> dict[str, Any]:
        return {
            "bay_id": self.bay_id,
            "state": self.state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "last_reading": self.last_reading,
            "last_dose_at": self.last_dose_at.isoformat() if self.last_dose_at else None,
            "last_ph_adjust_at": self.last_ph_adjust_at.isoformat() if self.last_ph_adjust_at else None,
            "pending_job_id": self.pending_job_id,
        }
