"""
Security Monitor Service

Responsibilities:
  - Subscribe to canonical security events from MQTT
  - Create and manage security incidents
  - Triage incidents by severity
  - Surface active incidents to ops-web
  - Propose investigation jobs to orchestrator (never auto-respond)

CRITICAL rule: No autonomous physical response.
This service INFORMS and QUEUES. Operators decide response.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .incident_queue import Incident, IncidentQueue, IncidentState, IncidentSeverity

logger = structlog.get_logger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_SECURITY", "security-monitor")
MQTT_PASS = os.getenv("MQTT_PASS_SECURITY", "")

_queue = IncidentQueue()


async def _mqtt_subscriber() -> None:
    """Subscribe to canonical security events."""
    try:
        import aiomqtt
    except ImportError:
        logger.warning("aiomqtt_not_available")
        return

    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USER,
                password=MQTT_PASS,
            ) as client:
                # Subscribe to all security events
                await client.subscribe("events/+/+/security.#")
                await client.subscribe("events/canonical/+/security.#")
                logger.info("security_monitor_mqtt_subscribed")

                async for message in client.messages:
                    try:
                        event = json.loads(message.payload)
                        event_type = event.get("event_type", "")
                        if event_type.startswith("security."):
                            _queue.create(event)
                    except Exception as e:
                        logger.error("mqtt_message_error", error=str(e))
        except Exception as e:
            logger.warning("security_mqtt_disconnected", error=str(e))
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("security_monitor_starting")
    task = asyncio.create_task(_mqtt_subscriber())
    yield
    task.cancel()


app = FastAPI(
    title="Security Monitor",
    description="Incident queue and triage — no autonomous physical response",
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
    active = _queue.list_active()
    critical = [i for i in active if i.severity == IncidentSeverity.CRITICAL]
    return {
        "status": "ok",
        "service": "security-monitor",
        "version": "0.1.0",
        "active_incidents": len(active),
        "critical_incidents": len(critical),
    }


@app.get("/incidents", tags=["incidents"])
async def list_incidents(
    active_only: bool = False,
    severity: str | None = None,
    limit: int = 50,
):
    """List security incidents."""
    if active_only:
        incidents = _queue.list_active()
    else:
        incidents = _queue.list_all(limit=limit)

    result = [i.to_dict() for i in incidents]
    if severity:
        result = [i for i in result if i["severity"] == severity.upper()]
    return result


@app.get("/incidents/{incident_id}", tags=["incidents"])
async def get_incident(incident_id: str):
    incident = _queue.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident.to_dict()


class AcknowledgeRequest(BaseModel):
    operator_id: str
    note: str | None = None


@app.post("/incidents/{incident_id}/acknowledge", tags=["incidents"])
async def acknowledge_incident(incident_id: str, req: AcknowledgeRequest):
    """Operator acknowledges an incident."""
    incident = _queue.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        # Triage first if still NEW
        if incident.state == IncidentState.NEW:
            incident.transition(IncidentState.TRIAGED, note="Operator reviewed")
        incident.transition(
            IncidentState.ACKNOWLEDGED,
            actor=req.operator_id,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return incident.to_dict()


class ResolveRequest(BaseModel):
    operator_id: str
    resolution: str


@app.post("/incidents/{incident_id}/resolve", tags=["incidents"])
async def resolve_incident(incident_id: str, req: ResolveRequest):
    """Operator resolves an incident."""
    incident = _queue.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        incident.transition(IncidentState.RESOLVED, actor=req.operator_id, note=req.resolution)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return incident.to_dict()


class SimulatedEvent(BaseModel):
    event_type: str
    asset_id: str
    severity: str = "WARNING"
    payload: dict = {}


@app.post("/incidents/simulate", tags=["incidents"])
async def simulate_event(event: SimulatedEvent):
    """Simulate a security event for testing."""
    import uuid
    from datetime import datetime
    canonical = {
        "event_id": str(uuid.uuid4()),
        "event_type": event.event_type,
        "source_service": "simulation",
        "asset_id": event.asset_id,
        "timestamp": datetime.utcnow().isoformat(),
        "severity": event.severity,
        "payload": event.payload,
    }
    incident = _queue.create(canonical)
    return incident.to_dict()
