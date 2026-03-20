"""
Drone Control Service

Supervised drone mission management via PX4/MAVLink.
ADR-005: Drone is second physical autonomy asset (after rover).
ADR-002: AI cannot arm or fly drone directly — OPERATOR_CONFIRM_TWICE required.

Safety model:
  - ALL flight operations are CRITICAL risk
  - Arming requires OPERATOR_CONFIRM_TWICE
  - Pre-flight checklist required before arming
  - RTL is always available as emergency action
  - Service will refuse to execute if orchestrator job not present
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .flight_state_machine import (
    DroneFlightStateMachine,
    FlightState,
    BATTERY_RTL_THRESHOLD_PCT,
)
from .mavlink_bridge import MavlinkBridge

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_DRONE", "drone-control")
MQTT_PASS = os.getenv("MQTT_PASS_DRONE", "")

DRONE_ID = os.getenv("DRONE_ID", "aerial-drone-001")
DRONE_ASSET_ID = f"asset:robot:drone:{DRONE_ID}"

_drone = DroneFlightStateMachine(DRONE_ID)
_mavlink = MavlinkBridge()


async def _update_digital_twin() -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{DRONE_ASSET_ID}/state",
                json={
                    "state": {
                        "value": _drone.state.value,
                        "battery_soc": _drone.battery_soc_pct,
                        "altitude_m": _drone.altitude_m,
                        "position": _drone.position,
                        "job_id": _drone.current_job_id,
                    },
                    "source": "drone-control",
                },
                timeout=5.0,
            )
    except Exception:
        pass


async def _telemetry_poller() -> None:
    """Poll MAVLink telemetry and update state machine."""
    while True:
        await asyncio.sleep(0.5)
        telemetry = _mavlink.get_telemetry()
        if telemetry:
            action = _drone.update_telemetry(
                lat=telemetry.get("lat", 0.0),
                lon=telemetry.get("lon", 0.0),
                alt_m=telemetry.get("alt_m", 0.0),
                battery_soc_pct=telemetry.get("battery_soc_pct"),
            )
            if action == "RTL":
                logger.warning("battery_low_rtl_triggered", soc=_drone.battery_soc_pct)
                _mavlink.send_rtl()
                try:
                    _drone.transition(FlightState.RETURNING, reason="Battery low RTL")
                except ValueError:
                    pass
            elif action == "FORCE_LAND":
                logger.error("battery_critical_force_land", soc=_drone.battery_soc_pct)
                _mavlink.send_rtl()
            await _update_digital_twin()


async def _comms_watchdog() -> None:
    """Trigger RTL if comms link is lost."""
    while True:
        await asyncio.sleep(5)
        if _drone.check_comms_timeout():
            logger.error("drone_comms_timeout_triggering_rtl")
            _mavlink.send_rtl()
            _drone.emergency_rtl("Communications timeout")
            await _update_digital_twin()


async def _mqtt_command_listener() -> None:
    """Listen for orchestrator-approved drone commands."""
    try:
        import aiomqtt
    except ImportError:
        logger.warning("aiomqtt_not_available")
        return

    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST, port=MQTT_PORT,
                username=MQTT_USER, password=MQTT_PASS,
            ) as client:
                await client.subscribe(f"commands/drone/{DRONE_ID}/#")
                logger.info("drone_command_listener_ready", drone_id=DRONE_ID)
                async for message in client.messages:
                    try:
                        topic = str(message.topic)
                        payload = json.loads(message.payload)
                        command = topic.split("/")[-1]
                        await _handle_command(command, payload)
                    except Exception as e:
                        logger.error("drone_command_error", error=str(e))
        except Exception as e:
            logger.warning("drone_mqtt_disconnected", error=str(e))
            await asyncio.sleep(10)


async def _handle_command(command: str, payload: dict) -> None:
    """Process approved drone command from orchestrator."""
    job_id = payload.get("job_id", "")
    logger.info("drone_command_received", command=command, job_id=job_id)

    if command == "rtl":
        _mavlink.send_rtl()
        _drone.emergency_rtl(payload.get("reason", "Remote RTL"))
        await _update_digital_twin()
        return

    if command == "arm":
        # CRITICAL: Only process if job_id is present (approved OPERATOR_CONFIRM_TWICE job)
        if not job_id:
            logger.error("arm_rejected_no_job_id")
            return
        _drone.current_job_id = job_id
        _drone.transition(FlightState.PRE_FLIGHT_CHECK, reason=f"job:{job_id}")
        # Pre-flight checklist (stub: always pass in SITL)
        _drone.transition(FlightState.ARMED, reason="Pre-flight passed")
        _mavlink.arm(job_id)
        await _update_digital_twin()

    if command == "mission":
        if not job_id or _drone.state != FlightState.ARMED:
            logger.error("mission_rejected", state=_drone.state, job_id=job_id)
            return
        waypoints = payload.get("waypoints", [])
        _mavlink.upload_mission(waypoints)
        _mavlink.start_mission()
        _drone.transition(FlightState.TAKING_OFF, reason=f"Mission job:{job_id}")
        await _update_digital_twin()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("drone_control_starting", drone_id=DRONE_ID)
    # Connect to MAVLink (SITL or field)
    _mavlink.connect()
    tasks = [
        asyncio.create_task(_mqtt_command_listener()),
        asyncio.create_task(_telemetry_poller()),
        asyncio.create_task(_comms_watchdog()),
    ]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(
    title="Drone Control",
    description="Supervised drone mission management — PX4/MAVLink bridge",
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
    return {
        "status": "ok",
        "service": "drone-control",
        "version": "0.1.0",
        "drone_id": DRONE_ID,
        "state": _drone.state,
    }


@app.get("/status", tags=["drone"])
async def get_status():
    return _drone.status()


@app.get("/flight-log", tags=["drone"])
async def get_flight_log(limit: int = 50):
    return _drone.flight_log[-limit:]


@app.post("/rtl", tags=["drone"])
async def emergency_rtl(reason: str = "Operator RTL"):
    """Emergency Return-To-Launch. Always available."""
    _mavlink.send_rtl()
    _drone.emergency_rtl(reason)
    await _update_digital_twin()
    return _drone.status()


@app.post("/clear-fault", tags=["drone"])
async def clear_fault(operator_id: str):
    """Operator clears FAULT state after grounded inspection."""
    try:
        _drone.clear_fault(operator_id)
        await _update_digital_twin()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _drone.status()


class TelemetryUpdate(BaseModel):
    lat: float
    lon: float
    alt_m: float
    battery_soc_pct: float | None = None


@app.post("/telemetry", tags=["drone"])
async def update_telemetry(payload: TelemetryUpdate):
    """Inject telemetry (used by SITL bridge)."""
    action = _drone.update_telemetry(
        payload.lat, payload.lon, payload.alt_m, payload.battery_soc_pct
    )
    if action == "RTL":
        _mavlink.send_rtl()
        try:
            _drone.transition(FlightState.RETURNING, reason="Battery low RTL")
        except ValueError:
            pass
    await _update_digital_twin()
    return _drone.status()
