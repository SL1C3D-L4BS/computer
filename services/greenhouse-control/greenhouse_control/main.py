"""
Greenhouse Control Service

Responsibilities:
  - Subscribe to MQTT telemetry for greenhouse zones
  - Maintain zone state machines
  - Evaluate frost/heat thresholds
  - PROPOSE jobs to orchestrator (never actuate directly)
  - Update digital-twin state for greenhouse assets
  - Expose health and zone status endpoints

What this service MUST NOT do:
  - Publish command topics to MQTT directly
  - Mutate job state
  - Make policy decisions (delegates to orchestrator)
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .state_machine import ZoneState, ZoneStateMachine

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_GREENHOUSE", "greenhouse-control")
MQTT_PASS = os.getenv("MQTT_PASS_GREENHOUSE", "")

# Zone state machines — keyed by zone_id
_zones: dict[str, ZoneStateMachine] = {}

# Temperature thresholds from site config (loaded at startup)
_FROST_THRESHOLD_C = float(os.getenv("FROST_THRESHOLD_CELSIUS", "2.0"))
_HIGH_TEMP_THRESHOLD_C = float(os.getenv("HIGH_TEMP_THRESHOLD_CELSIUS", "35.0"))


def _get_or_create_zone(zone_id: str) -> ZoneStateMachine:
    if zone_id not in _zones:
        _zones[zone_id] = ZoneStateMachine(zone_id)
        _zones[zone_id].transition(ZoneState.MONITORING, reason="Service startup")
    return _zones[zone_id]


async def _propose_job(job_type: str, zone_id: str, parameters: dict, risk_class: str = "MEDIUM") -> str | None:
    """
    Propose a job to the orchestrator.
    This is the ONLY way greenhouse-control can trigger actuation.
    Returns the job_id if proposal was accepted, None on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs",
                json={
                    "type": job_type,
                    "origin": "POLICY",
                    "target_asset_ids": parameters.get("target_asset_ids", []),
                    "risk_class": risk_class,
                    "parameters": parameters,
                    "requested_by": "greenhouse-control",
                },
                headers={"X-Service-ID": "greenhouse-control"},
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                logger.info(
                    "job_proposed",
                    job_id=job["job_id"],
                    job_type=job_type,
                    zone_id=zone_id,
                    state=job["state"],
                )
                return job["job_id"]
    except Exception as e:
        logger.error("job_proposal_failed", job_type=job_type, zone_id=zone_id, error=str(e))
    return None


async def _update_digital_twin_state(asset_id: str, state: dict) -> None:
    """Update asset state in digital-twin after receiving telemetry."""
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{asset_id}/state",
                json={"state": state, "source": "greenhouse-control"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("digital_twin_update_failed", asset_id=asset_id, error=str(e))


async def _process_telemetry(zone_id: str, readings: dict) -> None:
    """
    Process telemetry for a zone and propose jobs if thresholds are exceeded.
    This is the core control loop — evaluate → propose → wait for orchestrator.
    """
    zone = _get_or_create_zone(zone_id)
    zone.update_reading(readings)

    # Update digital-twin with latest sensor state
    temp_asset_id = f"asset:sensor:temp:{zone_id}"
    if "temperature_celsius" in readings:
        await _update_digital_twin_state(
            temp_asset_id,
            {"value": readings["temperature_celsius"], "unit": "celsius"},
        )

    humidity_asset_id = f"asset:sensor:humidity:{zone_id}"
    if "humidity_percent" in readings:
        await _update_digital_twin_state(
            humidity_asset_id,
            {"value": readings["humidity_percent"], "unit": "percent_rh"},
        )

    # Skip control evaluation if in SAFE_HOLD
    if zone.state == ZoneState.SAFE_HOLD:
        return

    # Skip if already actioning
    if zone.state in (ZoneState.HEATING, ZoneState.VENTILATING):
        return

    # Evaluate frost risk
    if zone.evaluate_frost_risk(_FROST_THRESHOLD_C):
        logger.warning("frost_risk_detected", zone_id=zone_id, readings=readings)
        heater_asset = f"asset:actuator:heater:{zone_id}"
        job_id = await _propose_job(
            job_type="greenhouse.heating.enable",
            zone_id=zone_id,
            parameters={
                "zone_id": zone_id,
                "target_asset_ids": [heater_asset],
                "reason": "frost_threshold_exceeded",
                "temperature_celsius": readings.get("temperature_celsius"),
                "threshold_celsius": _FROST_THRESHOLD_C,
                "duration_hours": 4,
            },
            risk_class="HIGH",  # Requires operator approval per site.yaml
        )
        if job_id:
            zone.pending_job_id = job_id

    # Evaluate overheating risk
    elif zone.evaluate_overheating_risk(_HIGH_TEMP_THRESHOLD_C):
        logger.warning("overheating_risk_detected", zone_id=zone_id, readings=readings)
        vent_asset = f"asset:actuator:vent:{zone_id}"
        job_id = await _propose_job(
            job_type="greenhouse.ventilation.enable",
            zone_id=zone_id,
            parameters={
                "zone_id": zone_id,
                "target_asset_ids": [vent_asset],
                "reason": "high_temp_threshold_exceeded",
                "temperature_celsius": readings.get("temperature_celsius"),
                "speed_percent": 100,
            },
            risk_class="MEDIUM",
        )
        if job_id:
            zone.pending_job_id = job_id


async def _mqtt_subscriber() -> None:
    """
    Subscribe to greenhouse sensor telemetry topics.
    Topic format: sensor/{zone_id}/temp, sensor/{zone_id}/humidity
    """
    try:
        import aiomqtt
    except ImportError:
        logger.warning("aiomqtt_not_available_skipping_mqtt")
        return

    try:
        async with aiomqtt.Client(
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASS,
        ) as client:
            await client.subscribe("sensor/greenhouse-+/+")
            logger.info("mqtt_subscribed", topic="sensor/greenhouse-+/+")
            async for message in client.messages:
                try:
                    import json
                    topic_parts = str(message.topic).split("/")
                    if len(topic_parts) >= 2:
                        zone_id = topic_parts[1]
                        payload = json.loads(message.payload)
                        await _process_telemetry(zone_id, payload)
                except Exception as e:
                    logger.error("mqtt_message_error", error=str(e))
    except Exception as e:
        logger.error("mqtt_connection_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("greenhouse_control_starting")
    # Initialize known zones from site config
    for zone_id in ["greenhouse-north", "greenhouse-south"]:
        _get_or_create_zone(zone_id)

    # Start MQTT subscriber in background
    task = asyncio.create_task(_mqtt_subscriber())
    yield
    task.cancel()
    logger.info("greenhouse_control_stopping")


app = FastAPI(
    title="Greenhouse Control",
    description="Greenhouse zone climate management — monitoring and job proposals only",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "greenhouse-control",
        "version": "0.1.0",
        "zones": len(_zones),
    }


@app.get("/zones", tags=["zones"])
async def list_zones():
    """Return status of all greenhouse zones."""
    return [zone.status() for zone in _zones.values()]


@app.get("/zones/{zone_id}", tags=["zones"])
async def get_zone(zone_id: str):
    """Return status of a specific zone."""
    if zone_id not in _zones:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return _zones[zone_id].status()


class TelemetryPayload(BaseModel):
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    co2_ppm: float | None = None


@app.post("/zones/{zone_id}/telemetry", tags=["zones"])
async def inject_telemetry(zone_id: str, payload: TelemetryPayload):
    """
    Inject telemetry for a zone (for testing and simulation).
    Production: telemetry comes from MQTT.
    """
    readings = {k: v for k, v in payload.model_dump().items() if v is not None}
    await _process_telemetry(zone_id, readings)
    return _get_or_create_zone(zone_id).status()


@app.post("/zones/{zone_id}/e-stop", tags=["zones"])
async def zone_e_stop(zone_id: str, reason: str = "Operator E-stop"):
    """Emergency stop a specific zone. Sets all actuators to safe state."""
    if zone_id not in _zones:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    _zones[zone_id].e_stop(reason)
    return _zones[zone_id].status()


@app.post("/zones/{zone_id}/clear-safe-hold", tags=["zones"])
async def clear_safe_hold(zone_id: str):
    """Operator clears a zone from SAFE_HOLD state."""
    if zone_id not in _zones:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    _zones[zone_id].clear_safe_hold()
    return _zones[zone_id].status()
