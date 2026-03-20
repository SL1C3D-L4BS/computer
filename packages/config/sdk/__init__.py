"""
site-config SDK — safe access to site.yaml for all services.

Usage:
  from config.sdk import get_site_config, get_zones, get_energy_tariff

Design rules (see docs/productization/site-config-boundary.md):
  - Core services MUST use this SDK; never import site.yaml directly
  - SDK reads from SITE_CONFIG_PATH env var or default repo location
  - All returned objects are typed Pydantic models
  - SDK is read-only; services may not mutate site config at runtime
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

_DEFAULT_SITE_CONFIG = (
    Path(__file__).parent.parent.parent.parent / "packages" / "config" / "site" / "site.yaml"
)


def _site_config_path() -> Path:
    env_path = os.getenv("SITE_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return _DEFAULT_SITE_CONFIG


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    path = _site_config_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


class ZoneConfig(BaseModel):
    zone_id: str
    name: str
    type: str
    area_sqft: float | None = None
    frost_threshold_celsius: float | None = None

    class Config:
        extra = "allow"


class TouWindow(BaseModel):
    days: list[str]
    start: str
    end: str


class TouRate(BaseModel):
    rate_per_kwh: float
    windows: list[TouWindow] = []


class TouSchedule(BaseModel):
    timezone: str
    peak: TouRate
    off_peak: TouRate


class EnergyConfig(BaseModel):
    utility: str | None = None
    tou_schedule: TouSchedule | None = None
    peak_shave_target_kw: float | None = None
    grid_charge_threshold_soc_pct: float | None = None
    discharge_reserve_soc_pct: float | None = None

    class Config:
        extra = "allow"


class FrostProtectionConfig(BaseModel):
    enabled: bool = False
    alert_threshold_celsius: float = 2.0
    critical_threshold_celsius: float = -2.0
    auto_heat_enable_threshold_celsius: float = 1.0
    heat_enable_risk_class: str = "HIGH"


class SiteConfig(BaseModel):
    site_id: str
    site_name: str
    timezone: str = "UTC"
    zones: list[ZoneConfig] = []
    energy: EnergyConfig | None = None
    frost_protection: FrostProtectionConfig | None = None

    class Config:
        extra = "allow"


def get_site_config() -> SiteConfig:
    """Return the full site configuration as a typed model."""
    raw = _load_raw()
    return SiteConfig.model_validate(raw)


def get_zones(zone_type: str | None = None) -> list[ZoneConfig]:
    """Return all zones, optionally filtered by type."""
    cfg = get_site_config()
    if zone_type:
        return [z for z in cfg.zones if z.type == zone_type]
    return cfg.zones


def get_zone(zone_id: str) -> ZoneConfig | None:
    """Return a specific zone by ID."""
    for zone in get_site_config().zones:
        if zone.zone_id == zone_id:
            return zone
    return None


def get_energy_config() -> EnergyConfig | None:
    """Return energy configuration including TOU tariff."""
    return get_site_config().energy


def get_frost_config() -> FrostProtectionConfig | None:
    """Return frost protection configuration."""
    return get_site_config().frost_protection


def get_current_tou_rate(hour: int, is_weekday: bool) -> float:
    """
    Return the current electricity rate based on time-of-use schedule.
    hour: 0-23 in local timezone
    is_weekday: True for Mon-Fri
    """
    energy = get_energy_config()
    if not energy or not energy.tou_schedule:
        return 0.10  # Default fallback rate

    tou = energy.tou_schedule

    if not is_weekday:
        return tou.off_peak.rate_per_kwh

    # Check if current hour falls in a peak window
    for window in tou.peak.windows:
        start_h = int(window.start.split(":")[0])
        end_h = int(window.end.split(":")[0])
        if start_h <= hour < end_h:
            return tou.peak.rate_per_kwh

    return tou.off_peak.rate_per_kwh
