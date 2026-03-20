"""
OSINT Provider Interface

Per ADR-008: OSINT providers are optional adapters, not core dependencies.
The system must operate fully without OSINT.

This module defines the abstract interface that all OSINT providers must implement.
Providers: PulsePoint Respond, Citizen, local law enforcement RSS feeds, weather alerts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class OsintIncidentCategory(str, Enum):
    FIRE = "fire"
    MEDICAL = "medical"
    POLICE = "police"
    WEATHER = "weather"
    TRAFFIC = "traffic"
    HAZMAT = "hazmat"
    UNKNOWN = "unknown"


class OsintIncident(BaseModel):
    """Normalized OSINT incident — provider-agnostic format."""
    incident_id: str
    provider: str
    category: OsintIncidentCategory
    title: str
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None  # Distance from site
    timestamp: datetime
    severity: str = "INFO"  # INFO | WARNING | CRITICAL
    raw: dict[str, Any] | None = None  # Original provider payload for audit


class OsintProvider(ABC):
    """Abstract base for all OSINT data providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier."""
        ...

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is enabled in site config."""
        ...

    @abstractmethod
    async def fetch_incidents(
        self,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
    ) -> list[OsintIncident]:
        """
        Fetch recent incidents within radius of site location.
        Must never raise (return empty list on failure).
        """
        ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return provider health status."""
        ...


class NullOsintProvider(OsintProvider):
    """
    No-op provider — used when OSINT is disabled.
    Ensures the system works without any OSINT configuration.
    """

    @property
    def provider_id(self) -> str:
        return "null"

    @property
    def enabled(self) -> bool:
        return False

    async def fetch_incidents(self, lat: float, lon: float, radius_km: float = 10.0) -> list:
        return []

    async def health_check(self) -> dict:
        return {"status": "disabled", "provider": "null"}


class PulsePointProvider(OsintProvider):
    """
    PulsePoint Respond API provider.
    Provides CAD (Computer-Aided Dispatch) data for fire/EMS incidents.
    Note: API availability varies by agency subscription.
    """

    def __init__(self, agency_id: str, api_key: str | None = None):
        self._agency_id = agency_id
        self._api_key = api_key

    @property
    def provider_id(self) -> str:
        return "pulsepoint"

    @property
    def enabled(self) -> bool:
        return bool(self._agency_id)

    async def fetch_incidents(
        self,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
    ) -> list[OsintIncident]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://web.pulsepoint.org/DB/giba.php",
                    params={"agency_id": self._agency_id},
                    headers={"User-Agent": "Computer-OSINT/1.0"},
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                incidents = []
                for item in data.get("incidents", {}).get("active", []):
                    lat_i = float(item.get("Latitude", 0))
                    lon_i = float(item.get("Longitude", 0))
                    dist = _haversine_km(lat, lon, lat_i, lon_i)
                    if dist > radius_km:
                        continue

                    category = _classify_pulsepoint(item.get("PulsePointIncidentCallType", ""))
                    incidents.append(OsintIncident(
                        incident_id=f"pp-{item.get('ID', '')}",
                        provider="pulsepoint",
                        category=category,
                        title=item.get("PulsePointIncidentCallType", "Unknown"),
                        description=item.get("FullDisplayAddress"),
                        latitude=lat_i,
                        longitude=lon_i,
                        distance_km=round(dist, 2),
                        timestamp=datetime.utcnow(),
                        severity="WARNING" if category in (OsintIncidentCategory.FIRE, OsintIncidentCategory.HAZMAT) else "INFO",
                        raw=item,
                    ))
                return incidents
        except Exception:
            return []

    async def health_check(self) -> dict:
        return {"status": "ok", "provider": "pulsepoint", "agency_id": self._agency_id}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _classify_pulsepoint(call_type: str) -> OsintIncidentCategory:
    ct = call_type.upper()
    if any(k in ct for k in ["FIRE", "SMOKE", "BRUSH"]):
        return OsintIncidentCategory.FIRE
    if any(k in ct for k in ["MEDICAL", "EMS", "CARDIAC", "TRAUMA"]):
        return OsintIncidentCategory.MEDICAL
    if any(k in ct for k in ["POLICE", "CRIME", "SHOOTING"]):
        return OsintIncidentCategory.POLICE
    if any(k in ct for k in ["HAZMAT", "SPILL", "CHEMICAL"]):
        return OsintIncidentCategory.HAZMAT
    return OsintIncidentCategory.UNKNOWN


def get_providers_from_env() -> list[OsintProvider]:
    """
    Initialize OSINT providers from environment config.
    Returns NullOsintProvider if none configured (ADR-008: optional).
    """
    import os
    providers: list[OsintProvider] = []

    pp_agency = os.getenv("OSINT_PULSEPOINT_AGENCY_ID")
    if pp_agency:
        providers.append(PulsePointProvider(agency_id=pp_agency))

    if not providers:
        providers.append(NullOsintProvider())

    return providers
