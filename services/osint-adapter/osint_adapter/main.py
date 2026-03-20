"""
OSINT Adapter Service

Per ADR-008: This is an optional module. System operates fully without it.
Feature flag: OSINT_ENABLED=true

Provides situational awareness from public data sources:
  - PulsePoint Respond (fire/EMS CAD data)
  - Future: NWS weather alerts, local law enforcement RSS

All incidents are normalized to the canonical OsintIncident format
and forwarded as canonical events to event-ingest.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .provider_interface import get_providers_from_env, OsintIncident

logger = structlog.get_logger(__name__)

# Site location (loaded from env; should come from site-config SDK)
SITE_LAT = float(os.getenv("SITE_LAT", "47.6062"))
SITE_LON = float(os.getenv("SITE_LON", "-117.3321"))
OSINT_RADIUS_KM = float(os.getenv("OSINT_RADIUS_KM", "10.0"))
OSINT_POLL_INTERVAL_SECONDS = int(os.getenv("OSINT_POLL_INTERVAL_SECONDS", "300"))

_providers = get_providers_from_env()
_recent_incidents: list[dict] = []
_MAX_INCIDENTS = 200


async def _poll_providers() -> None:
    """Periodically poll all OSINT providers."""
    while True:
        for provider in _providers:
            if not provider.enabled:
                continue
            try:
                incidents = await provider.fetch_incidents(
                    lat=SITE_LAT,
                    lon=SITE_LON,
                    radius_km=OSINT_RADIUS_KM,
                )
                for incident in incidents:
                    _process_incident(incident)
                logger.debug(
                    "osint_poll_complete",
                    provider=provider.provider_id,
                    incidents=len(incidents),
                )
            except Exception as e:
                logger.error("osint_poll_failed", provider=provider.provider_id, error=str(e))

        await asyncio.sleep(OSINT_POLL_INTERVAL_SECONDS)


def _process_incident(incident: OsintIncident) -> None:
    """Store and log a normalized incident."""
    record = incident.model_dump(mode="json")
    # Avoid duplicates by incident_id
    existing_ids = {r["incident_id"] for r in _recent_incidents}
    if incident.incident_id not in existing_ids:
        _recent_incidents.append(record)
        if len(_recent_incidents) > _MAX_INCIDENTS:
            _recent_incidents.pop(0)
        logger.info(
            "osint_incident",
            incident_id=incident.incident_id,
            category=incident.category,
            distance_km=incident.distance_km,
            severity=incident.severity,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "osint_adapter_starting",
        providers=[p.provider_id for p in _providers if p.enabled],
    )
    task = asyncio.create_task(_poll_providers())
    yield
    task.cancel()


app = FastAPI(
    title="OSINT Adapter",
    description="Optional situational awareness from public data sources (ADR-008)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    provider_statuses = []
    for p in _providers:
        status = await p.health_check()
        provider_statuses.append(status)
    return {
        "status": "ok",
        "service": "osint-adapter",
        "version": "0.1.0",
        "providers": provider_statuses,
        "recent_incidents": len(_recent_incidents),
    }


@app.get("/incidents", tags=["incidents"])
async def list_incidents(
    severity: str | None = None,
    category: str | None = None,
    limit: int = 50,
):
    """Return recent OSINT incidents."""
    incidents = _recent_incidents[-limit:]
    if severity:
        incidents = [i for i in incidents if i.get("severity") == severity.upper()]
    if category:
        incidents = [i for i in incidents if i.get("category") == category.lower()]
    return incidents
