"""
Rover mission state machine.

States:
  IDLE → DISPATCHING → NAVIGATING → AT_WAYPOINT → NAVIGATING → ... → RETURNING → DOCKED
  Any state → SAFE_STOP (e-stop or loss-of-comms)

Safety rules (per docs/safety/e-stop-and-fail-safe.md):
  - E-stop brings rover to immediate stop and holds
  - Communications loss triggers safe-stop after 30s
  - Battery low (<15%) triggers auto return-to-home (RTH)
  - Mission requires OPERATOR_REQUIRED approval before dispatch
  - All mission steps are logged to orchestrator audit

ADR-005: Rover before drone; this is the first physical autonomy asset.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MissionState(str, Enum):
    IDLE = "IDLE"
    DISPATCHING = "DISPATCHING"
    NAVIGATING = "NAVIGATING"
    AT_WAYPOINT = "AT_WAYPOINT"
    COLLECTING_DATA = "COLLECTING_DATA"
    RETURNING = "RETURNING"
    DOCKED = "DOCKED"
    SAFE_STOP = "SAFE_STOP"
    FAULT = "FAULT"


ALLOWED_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.IDLE: {MissionState.DISPATCHING, MissionState.SAFE_STOP},
    MissionState.DISPATCHING: {MissionState.NAVIGATING, MissionState.SAFE_STOP, MissionState.FAULT},
    MissionState.NAVIGATING: {
        MissionState.AT_WAYPOINT,
        MissionState.RETURNING,
        MissionState.SAFE_STOP,
        MissionState.FAULT,
    },
    MissionState.AT_WAYPOINT: {
        MissionState.COLLECTING_DATA,
        MissionState.NAVIGATING,
        MissionState.RETURNING,
        MissionState.SAFE_STOP,
    },
    MissionState.COLLECTING_DATA: {
        MissionState.AT_WAYPOINT,
        MissionState.NAVIGATING,
        MissionState.SAFE_STOP,
    },
    MissionState.RETURNING: {MissionState.DOCKED, MissionState.SAFE_STOP, MissionState.FAULT},
    MissionState.DOCKED: {MissionState.IDLE},
    MissionState.SAFE_STOP: {MissionState.IDLE},  # Operator must clear
    MissionState.FAULT: {MissionState.IDLE},       # Operator must clear
}

# Safety thresholds
BATTERY_RTH_THRESHOLD_PCT = 15.0
BATTERY_ABORT_THRESHOLD_PCT = 10.0
COMMS_TIMEOUT_SECONDS = 30.0


class RoverMissionStateMachine:
    def __init__(self, rover_id: str):
        self.rover_id = rover_id
        self.state = MissionState.IDLE
        self.state_entered_at = datetime.utcnow()
        self.current_job_id: str | None = None
        self.current_mission: dict[str, Any] | None = None
        self.waypoints: list[dict] = []
        self.current_waypoint_idx: int = 0
        self.battery_soc_pct: float | None = None
        self.last_position: dict | None = None
        self.last_comms_at: datetime = datetime.utcnow()
        self.mission_log: list[dict] = []
        self._log = logger.bind(rover_id=rover_id)

    def transition(self, target: MissionState, *, reason: str | None = None) -> MissionState:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Rover {self.rover_id}: cannot transition {self.state} → {target}")
        prev = self.state
        self.state = target
        self.state_entered_at = datetime.utcnow()
        self._log_event("state_transition", from_state=prev, to_state=target, reason=reason)
        return target

    def e_stop(self, reason: str = "E-stop") -> None:
        """Emergency stop from any state."""
        prev = self.state
        self.state = MissionState.SAFE_STOP
        self.state_entered_at = datetime.utcnow()
        self._log_event("e_stop", from_state=prev, reason=reason)
        self._log.warning("rover_e_stop", from_state=prev, reason=reason)

    def clear_fault(self, operator_id: str) -> None:
        """Operator clears SAFE_STOP or FAULT to allow mission resumption."""
        if self.state not in (MissionState.SAFE_STOP, MissionState.FAULT):
            raise ValueError(f"Rover {self.rover_id} not in a clearable state: {self.state}")
        self.transition(MissionState.IDLE, reason=f"Cleared by {operator_id}")

    def update_battery(self, soc_pct: float) -> bool:
        """
        Update battery SOC. Returns True if RTH should be triggered.
        Caller must submit RTH job to orchestrator if True.
        """
        self.battery_soc_pct = soc_pct
        if soc_pct <= BATTERY_ABORT_THRESHOLD_PCT:
            if self.state not in (MissionState.IDLE, MissionState.SAFE_STOP, MissionState.DOCKED):
                self.e_stop(f"Battery critically low: {soc_pct}%")
            return False
        return (
            soc_pct <= BATTERY_RTH_THRESHOLD_PCT
            and self.state not in (MissionState.IDLE, MissionState.RETURNING, MissionState.DOCKED, MissionState.SAFE_STOP)
        )

    def update_position(self, lat: float, lon: float, heading: float | None = None) -> None:
        self.last_position = {"lat": lat, "lon": lon, "heading": heading}
        self.last_comms_at = datetime.utcnow()

    def check_comms_timeout(self) -> bool:
        """Returns True if communications timeout exceeded (should trigger safe-stop)."""
        elapsed = (datetime.utcnow() - self.last_comms_at).total_seconds()
        return elapsed > COMMS_TIMEOUT_SECONDS and self.state not in (
            MissionState.IDLE, MissionState.DOCKED, MissionState.SAFE_STOP
        )

    def _log_event(self, event_type: str, **kwargs) -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "state": self.state,
            "job_id": self.current_job_id,
            **kwargs,
        }
        self.mission_log.append(entry)
        if len(self.mission_log) > 1000:
            self.mission_log = self.mission_log[-500:]

    def status(self) -> dict[str, Any]:
        return {
            "rover_id": self.rover_id,
            "state": self.state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "current_job_id": self.current_job_id,
            "current_waypoint_idx": self.current_waypoint_idx,
            "total_waypoints": len(self.waypoints),
            "battery_soc_pct": self.battery_soc_pct,
            "last_position": self.last_position,
            "last_comms_at": self.last_comms_at.isoformat(),
        }
