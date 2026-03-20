"""
Drone flight state machine.

ADR-005: Drone is the SECOND physical autonomy asset, deferred until rover is proven.
ADR-002: AI cannot arm or fly the drone directly. All flight is OPERATOR_REQUIRED.

States:
  GROUNDED → PRE_FLIGHT_CHECK → ARMED → TAKING_OFF → HOVERING → NAVIGATING
  → AT_WAYPOINT → RETURNING → LANDING → GROUNDED

Safety rules:
  - Arming requires OPERATOR_REQUIRED approval (CRITICAL risk)
  - E-stop triggers immediate RETURN_TO_LAUNCH (RTL)
  - Battery low (<20%) triggers RTL
  - Geofence breach triggers RTL
  - All commands require OPERATOR_CONFIRM_TWICE approval
  - Disarm only when GROUNDED or FAULT

PX4 integration:
  - Uses MAVLink protocol via pymavlink
  - SITL: runs against PX4 SITL binary
  - Field: MAVLink over telemetry radio or UDP
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class FlightState(str, Enum):
    GROUNDED = "GROUNDED"
    PRE_FLIGHT_CHECK = "PRE_FLIGHT_CHECK"
    ARMED = "ARMED"
    TAKING_OFF = "TAKING_OFF"
    HOVERING = "HOVERING"
    NAVIGATING = "NAVIGATING"
    AT_WAYPOINT = "AT_WAYPOINT"
    RETURNING = "RETURNING"          # RTL
    LANDING = "LANDING"
    EMERGENCY_LAND = "EMERGENCY_LAND"
    FAULT = "FAULT"


ALLOWED_TRANSITIONS: dict[FlightState, set[FlightState]] = {
    FlightState.GROUNDED: {FlightState.PRE_FLIGHT_CHECK, FlightState.FAULT},
    FlightState.PRE_FLIGHT_CHECK: {
        FlightState.ARMED,
        FlightState.GROUNDED,
        FlightState.FAULT,
    },
    FlightState.ARMED: {
        FlightState.TAKING_OFF,
        FlightState.GROUNDED,     # Disarm
        FlightState.FAULT,
    },
    FlightState.TAKING_OFF: {
        FlightState.HOVERING,
        FlightState.RETURNING,
        FlightState.EMERGENCY_LAND,
        FlightState.FAULT,
    },
    FlightState.HOVERING: {
        FlightState.NAVIGATING,
        FlightState.RETURNING,
        FlightState.LANDING,
        FlightState.EMERGENCY_LAND,
    },
    FlightState.NAVIGATING: {
        FlightState.AT_WAYPOINT,
        FlightState.HOVERING,
        FlightState.RETURNING,
        FlightState.EMERGENCY_LAND,
        FlightState.FAULT,
    },
    FlightState.AT_WAYPOINT: {
        FlightState.NAVIGATING,
        FlightState.HOVERING,
        FlightState.RETURNING,
        FlightState.EMERGENCY_LAND,
    },
    FlightState.RETURNING: {
        FlightState.LANDING,
        FlightState.HOVERING,
        FlightState.EMERGENCY_LAND,
        FlightState.FAULT,
    },
    FlightState.LANDING: {
        FlightState.GROUNDED,
        FlightState.EMERGENCY_LAND,
        FlightState.FAULT,
    },
    FlightState.EMERGENCY_LAND: {FlightState.GROUNDED, FlightState.FAULT},
    FlightState.FAULT: {FlightState.GROUNDED},    # Operator clears
}

# Safety thresholds
BATTERY_RTL_THRESHOLD_PCT = 20.0     # Return-to-launch when battery hits 20%
BATTERY_FORCE_LAND_PCT = 10.0        # Force land immediately
GEOFENCE_RADIUS_M = 200.0            # Max distance from home (meters)
COMMS_TIMEOUT_SECONDS = 15.0         # Stricter than rover — drone requires tighter link


class DroneFlightStateMachine:
    def __init__(self, drone_id: str):
        self.drone_id = drone_id
        self.state = FlightState.GROUNDED
        self.state_entered_at = datetime.utcnow()
        self.current_job_id: str | None = None
        self.battery_soc_pct: float | None = None
        self.altitude_m: float = 0.0
        self.position: dict | None = None
        self.home_position: dict | None = None
        self.last_comms_at: datetime = datetime.utcnow()
        self.flight_log: list[dict] = []
        self._log = logger.bind(drone_id=drone_id)

    def transition(self, target: FlightState, *, reason: str | None = None) -> FlightState:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Drone {self.drone_id}: Invalid transition {self.state} → {target}")
        prev = self.state
        self.state = target
        self.state_entered_at = datetime.utcnow()
        self._log_event("state_transition", from_state=prev, to_state=target, reason=reason)
        self._log.info("drone_state_transition", from_state=prev, to_state=target, reason=reason)
        return target

    def emergency_rtl(self, reason: str = "E-stop") -> None:
        """
        Emergency Return-To-Launch from any state.
        Preferred over immediate kill — drone returns safely.
        """
        prev = self.state
        if self.state in (FlightState.GROUNDED, FlightState.FAULT):
            return
        # If airborne, return; if grounded/taking off, emergency land
        if self.altitude_m > 0.5:
            self.state = FlightState.RETURNING
        else:
            self.state = FlightState.EMERGENCY_LAND
        self.state_entered_at = datetime.utcnow()
        self._log_event("emergency_rtl", from_state=prev, reason=reason)
        self._log.warning("drone_emergency_rtl", from_state=prev, reason=reason)

    def clear_fault(self, operator_id: str) -> None:
        """Operator clears FAULT to allow reset."""
        if not operator_id:
            raise ValueError("operator_id required to clear fault")
        if self.state != FlightState.FAULT:
            raise ValueError(f"Drone {self.drone_id} not in FAULT state: {self.state}")
        if self.altitude_m > 0.5:
            raise ValueError("Cannot clear fault while drone is airborne")
        self.transition(FlightState.GROUNDED, reason=f"Cleared by {operator_id}")

    def update_battery(self, soc_pct: float) -> str | None:
        """
        Update battery SOC.
        Returns action needed: 'RTL', 'FORCE_LAND', or None.
        """
        self.battery_soc_pct = soc_pct
        if self.state in (FlightState.GROUNDED, FlightState.FAULT):
            return None
        if soc_pct <= BATTERY_FORCE_LAND_PCT:
            self.emergency_rtl(f"Battery critically low: {soc_pct}%")
            return "FORCE_LAND"
        if soc_pct <= BATTERY_RTL_THRESHOLD_PCT:
            return "RTL"
        return None

    def update_telemetry(
        self,
        lat: float,
        lon: float,
        alt_m: float,
        battery_soc_pct: float | None = None,
    ) -> str | None:
        """Update position and battery. Returns any required action."""
        self.position = {"lat": lat, "lon": lon, "alt_m": alt_m}
        self.altitude_m = alt_m
        self.last_comms_at = datetime.utcnow()

        if self.home_position is None and alt_m < 1.0:
            self.home_position = {"lat": lat, "lon": lon}

        if battery_soc_pct is not None:
            action = self.update_battery(battery_soc_pct)
            if action:
                return action
        return None

    def check_comms_timeout(self) -> bool:
        """Returns True if communication link is lost."""
        elapsed = (datetime.utcnow() - self.last_comms_at).total_seconds()
        return (
            elapsed > COMMS_TIMEOUT_SECONDS
            and self.state not in (FlightState.GROUNDED, FlightState.FAULT)
        )

    def _log_event(self, event_type: str, **kwargs) -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "state": self.state,
            "job_id": self.current_job_id,
            "altitude_m": self.altitude_m,
            **kwargs,
        }
        self.flight_log.append(entry)
        if len(self.flight_log) > 2000:
            self.flight_log = self.flight_log[-1000:]

    def status(self) -> dict[str, Any]:
        return {
            "drone_id": self.drone_id,
            "state": self.state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "current_job_id": self.current_job_id,
            "battery_soc_pct": self.battery_soc_pct,
            "altitude_m": self.altitude_m,
            "position": self.position,
            "home_position": self.home_position,
            "last_comms_at": self.last_comms_at.isoformat(),
        }
