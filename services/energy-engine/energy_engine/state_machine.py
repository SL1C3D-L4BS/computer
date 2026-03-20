"""
Energy management state machine.

States represent the current dispatch strategy for the site's battery/solar system.

States:
  NORMAL — balanced grid/solar/battery based on TOU and SOC
  PEAK_SHAVING — discharging battery to reduce grid draw during TOU peak
  SOLAR_CHARGING — preferentially charging battery from solar excess
  GRID_CHARGING — grid-charging during off-peak (overnight cheap rate)
  CONSERVING — holding battery above reserve threshold (storm prep, outage risk)
  EMERGENCY_POWER — grid outage; running on battery + solar only
  SAFE_HOLD — fault state; system reverts to inverter auto-mode

Transitions driven by:
  - Time-of-use schedule (from site config)
  - Battery SOC readings
  - Grid power events
  - Solar forecast
  - Operator overrides (all via orchestrator jobs)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class EnergyState(str, Enum):
    NORMAL = "NORMAL"
    PEAK_SHAVING = "PEAK_SHAVING"
    SOLAR_CHARGING = "SOLAR_CHARGING"
    GRID_CHARGING = "GRID_CHARGING"
    CONSERVING = "CONSERVING"
    EMERGENCY_POWER = "EMERGENCY_POWER"
    SAFE_HOLD = "SAFE_HOLD"


ALLOWED_TRANSITIONS: dict[EnergyState, set[EnergyState]] = {
    EnergyState.NORMAL: {
        EnergyState.PEAK_SHAVING,
        EnergyState.SOLAR_CHARGING,
        EnergyState.GRID_CHARGING,
        EnergyState.CONSERVING,
        EnergyState.EMERGENCY_POWER,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.PEAK_SHAVING: {
        EnergyState.NORMAL,
        EnergyState.CONSERVING,
        EnergyState.EMERGENCY_POWER,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.SOLAR_CHARGING: {
        EnergyState.NORMAL,
        EnergyState.PEAK_SHAVING,
        EnergyState.CONSERVING,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.GRID_CHARGING: {
        EnergyState.NORMAL,
        EnergyState.CONSERVING,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.CONSERVING: {
        EnergyState.NORMAL,
        EnergyState.PEAK_SHAVING,
        EnergyState.EMERGENCY_POWER,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.EMERGENCY_POWER: {
        EnergyState.NORMAL,
        EnergyState.CONSERVING,
        EnergyState.SAFE_HOLD,
    },
    EnergyState.SAFE_HOLD: {EnergyState.NORMAL},
}


class EnergyStateMachine:
    def __init__(self):
        self.state = EnergyState.NORMAL
        self.state_entered_at = datetime.utcnow()
        self.last_grid_kw: float | None = None
        self.last_solar_kw: float | None = None
        self.last_battery_soc_pct: float | None = None
        self.last_reading_at: datetime | None = None
        self._log = logger.bind(service="energy-engine")

    def transition(self, target: EnergyState, *, reason: str | None = None) -> EnergyState:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Cannot transition energy state from {self.state} to {target}")
        prev = self.state
        self.state = target
        self.state_entered_at = datetime.utcnow()
        self._log.info("energy_state_transition", from_state=prev, to_state=target, reason=reason)
        return target

    def update_readings(
        self,
        grid_kw: float | None = None,
        solar_kw: float | None = None,
        battery_soc_pct: float | None = None,
    ) -> None:
        if grid_kw is not None:
            self.last_grid_kw = grid_kw
        if solar_kw is not None:
            self.last_solar_kw = solar_kw
        if battery_soc_pct is not None:
            self.last_battery_soc_pct = battery_soc_pct
        self.last_reading_at = datetime.utcnow()

    def evaluate_peak_shave_opportunity(
        self,
        peak_shave_target_kw: float = 5.0,
        discharge_reserve_soc_pct: float = 15.0,
        is_tou_peak: bool = False,
    ) -> bool:
        """
        Returns True if peak shaving should be proposed.
        Caller must submit job to orchestrator.
        """
        if not is_tou_peak:
            return False
        if self.last_grid_kw is None or self.last_battery_soc_pct is None:
            return False
        if self.last_battery_soc_pct <= discharge_reserve_soc_pct:
            return False
        return self.last_grid_kw > peak_shave_target_kw

    def evaluate_grid_charge_opportunity(
        self,
        grid_charge_threshold_soc_pct: float = 20.0,
        is_tou_off_peak: bool = False,
    ) -> bool:
        """Returns True if overnight grid charging should be proposed."""
        if not is_tou_off_peak:
            return False
        if self.last_battery_soc_pct is None:
            return False
        return self.last_battery_soc_pct < grid_charge_threshold_soc_pct

    def evaluate_solar_excess(self, export_threshold_kw: float = 1.0) -> bool:
        """Returns True if there is meaningful solar export to use for charging."""
        if self.last_solar_kw is None or self.last_grid_kw is None:
            return False
        # Net export = solar - consumption
        net_export = self.last_solar_kw - abs(min(0, self.last_grid_kw or 0))
        return net_export > export_threshold_kw

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "last_grid_kw": self.last_grid_kw,
            "last_solar_kw": self.last_solar_kw,
            "last_battery_soc_pct": self.last_battery_soc_pct,
            "last_reading_at": self.last_reading_at.isoformat() if self.last_reading_at else None,
        }
