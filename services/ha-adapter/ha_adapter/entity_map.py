"""
HA entity map — translates Home Assistant entity IDs to canonical asset IDs.

This is the ONLY place where vendor entity_id strings appear.
Core services never see entity_ids.

See ADR-003 (HA not system of record) and ADR-010 (capability model).
"""
from __future__ import annotations

from typing import Any


class EntityMapping:
    """Maps a HA entity_id to a canonical asset_id and event type."""

    def __init__(
        self,
        entity_id: str,
        asset_id: str,
        event_type: str,
        state_key: str = "value",
        unit: str | None = None,
        transform: Any | None = None,
    ):
        self.entity_id = entity_id
        self.asset_id = asset_id
        self.event_type = event_type
        self.state_key = state_key
        self.unit = unit
        self.transform = transform  # Optional callable to normalize value

    def to_canonical_state(self, ha_state: str, ha_attributes: dict) -> dict:
        """Convert HA state to canonical state dict."""
        value = ha_state
        if self.transform:
            value = self.transform(ha_state, ha_attributes)
        state = {self.state_key: value}
        if self.unit:
            state["unit"] = self.unit
        return state


def _float_or_none(v: str, _attrs: dict) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _on_off_to_bool(v: str, _attrs: dict) -> bool:
    return v.lower() in ("on", "true", "open", "home")


# ── Entity map — add entries as HA entities are configured ────────────────────
ENTITY_MAP: dict[str, EntityMapping] = {
    # Temperature sensors
    "sensor.greenhouse_north_temp": EntityMapping(
        entity_id="sensor.greenhouse_north_temp",
        asset_id="asset:sensor:temp:greenhouse-north",
        event_type="sensor.temperature.updated",
        state_key="value",
        unit="celsius",
        transform=_float_or_none,
    ),
    "sensor.greenhouse_south_temp": EntityMapping(
        entity_id="sensor.greenhouse_south_temp",
        asset_id="asset:sensor:temp:greenhouse-south",
        event_type="sensor.temperature.updated",
        state_key="value",
        unit="celsius",
        transform=_float_or_none,
    ),
    # Humidity sensors
    "sensor.greenhouse_north_humidity": EntityMapping(
        entity_id="sensor.greenhouse_north_humidity",
        asset_id="asset:sensor:humidity:greenhouse-north",
        event_type="sensor.humidity.updated",
        state_key="value",
        unit="percent_rh",
        transform=_float_or_none,
    ),
    # Energy meters
    "sensor.grid_energy_import": EntityMapping(
        entity_id="sensor.grid_energy_import",
        asset_id="asset:sensor:energy:grid-meter",
        event_type="sensor.energy.updated",
        state_key="value",
        unit="kW",
        transform=_float_or_none,
    ),
    "sensor.solar_production_kw": EntityMapping(
        entity_id="sensor.solar_production_kw",
        asset_id="asset:sensor:energy:solar-production",
        event_type="sensor.energy.updated",
        state_key="value",
        unit="kW",
        transform=_float_or_none,
    ),
    # Battery storage
    "sensor.bluetti_ac300_1_soc": EntityMapping(
        entity_id="sensor.bluetti_ac300_1_soc",
        asset_id="asset:storage:battery:bluetti-ac300-1",
        event_type="sensor.battery_soc.updated",
        state_key="soc_percent",
        unit="percent",
        transform=_float_or_none,
    ),
    "sensor.bluetti_ac300_2_soc": EntityMapping(
        entity_id="sensor.bluetti_ac300_2_soc",
        asset_id="asset:storage:battery:bluetti-ac300-2",
        event_type="sensor.battery_soc.updated",
        state_key="soc_percent",
        unit="percent",
        transform=_float_or_none,
    ),
    # Actuator states (read-only — ha-adapter only reads HA state)
    "switch.irrigation_valve_zone_1": EntityMapping(
        entity_id="switch.irrigation_valve_zone_1",
        asset_id="asset:actuator:valve:irrigation:zone-1",
        event_type="actuator.state.updated",
        state_key="value",
        transform=lambda v, _: "open" if _on_off_to_bool(v, _) else "closed",
    ),
}


def get_mapping(entity_id: str) -> EntityMapping | None:
    return ENTITY_MAP.get(entity_id)


def get_all_entity_ids() -> list[str]:
    return list(ENTITY_MAP.keys())
