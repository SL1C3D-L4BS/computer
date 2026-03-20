"""
Greenhouse zone state machine.

States: IDLE → MONITORING → HEATING | VENTILATING | IRRIGATING → MONITORING → IDLE
Each zone runs its own state machine instance.

Rules:
  - State transitions are deterministic and logged
  - Heater and vent are mutually exclusive per zone (not both running simultaneously)
  - All actuations go through orchestrator (never direct MQTT publish)
  - E-stop transitions to SAFE_HOLD from any state
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ZoneState(str, Enum):
    IDLE = "IDLE"
    MONITORING = "MONITORING"
    HEATING = "HEATING"
    VENTILATING = "VENTILATING"
    IRRIGATING = "IRRIGATING"
    SAFE_HOLD = "SAFE_HOLD"  # E-stop or fault — all actuators off, waiting for operator


ALLOWED_TRANSITIONS: dict[ZoneState, set[ZoneState]] = {
    ZoneState.IDLE: {ZoneState.MONITORING, ZoneState.SAFE_HOLD},
    ZoneState.MONITORING: {
        ZoneState.HEATING,
        ZoneState.VENTILATING,
        ZoneState.IRRIGATING,
        ZoneState.IDLE,
        ZoneState.SAFE_HOLD,
    },
    ZoneState.HEATING: {ZoneState.MONITORING, ZoneState.SAFE_HOLD},
    ZoneState.VENTILATING: {ZoneState.MONITORING, ZoneState.SAFE_HOLD},
    ZoneState.IRRIGATING: {ZoneState.MONITORING, ZoneState.SAFE_HOLD},
    ZoneState.SAFE_HOLD: {ZoneState.IDLE},  # Only operator can clear SAFE_HOLD
}


class ZoneStateMachine:
    def __init__(self, zone_id: str):
        self.zone_id = zone_id
        self.state = ZoneState.IDLE
        self.state_entered_at: datetime = datetime.utcnow()
        self.last_reading: dict[str, Any] = {}
        self.pending_job_id: str | None = None
        self._log = logger.bind(zone_id=zone_id)

    def transition(self, target: ZoneState, *, reason: str | None = None) -> ZoneState:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(
                f"Zone {self.zone_id}: cannot transition from {self.state} to {target}"
            )
        prev = self.state
        self.state = target
        self.state_entered_at = datetime.utcnow()
        if target != ZoneState.HEATING and target != ZoneState.VENTILATING:
            self.pending_job_id = None
        self._log.info(
            "zone_state_transition",
            from_state=prev,
            to_state=target,
            reason=reason,
        )
        return target

    def e_stop(self, reason: str = "E-stop") -> None:
        """Force transition to SAFE_HOLD from any state."""
        prev = self.state
        self.state = ZoneState.SAFE_HOLD
        self.state_entered_at = datetime.utcnow()
        self.pending_job_id = None
        self._log.warning("zone_e_stop", from_state=prev, reason=reason)

    def clear_safe_hold(self) -> None:
        """Operator clears SAFE_HOLD to resume normal monitoring."""
        if self.state != ZoneState.SAFE_HOLD:
            raise ValueError(f"Zone {self.zone_id} is not in SAFE_HOLD")
        self.transition(ZoneState.IDLE, reason="Operator cleared safe hold")

    def update_reading(self, readings: dict[str, Any]) -> None:
        """Record latest telemetry readings for this zone."""
        self.last_reading = {**readings, "received_at": datetime.utcnow().isoformat()}

    def evaluate_frost_risk(self, frost_threshold_celsius: float = 2.0) -> bool:
        """
        Returns True if current temperature reading indicates frost risk.
        Caller must submit job to orchestrator — this method NEVER actuates directly.
        """
        temp = self.last_reading.get("temperature_celsius")
        if temp is None:
            return False
        return float(temp) <= frost_threshold_celsius

    def evaluate_overheating_risk(self, high_temp_celsius: float = 35.0) -> bool:
        """Returns True if temperature is above safe operating range."""
        temp = self.last_reading.get("temperature_celsius")
        if temp is None:
            return False
        return float(temp) >= high_temp_celsius

    def status(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "state": self.state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "last_reading": self.last_reading,
            "pending_job_id": self.pending_job_id,
        }
