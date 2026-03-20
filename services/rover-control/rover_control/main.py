"""
Rover Control Service

Bridges orchestrator-approved jobs to ROS2 Nav2 navigation stack.

Architecture:
  - Orchestrator dispatches approved rover.mission.* jobs via MQTT command topic
  - rover-control receives commands, validates, dispatches to Nav2
  - Nav2 feedback published back to orchestrator via MQTT telemetry
  - Digital-twin updated with rover position and state

Safety:
  - E-stop command immediately halts all navigation
  - Battery low (<15%) triggers auto RTH job proposal
  - Comms loss (>30s) triggers safe-stop
  - All mission steps logged to audit

ROS2 Integration:
  - In simulation: ros2 lifecycle node, Gazebo SITL
  - In field: direct Nav2 action server calls
  - ros2 bridge is isolated in ros2_ws/src/rover_control/
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

from .mission_state_machine import MissionState, RoverMissionStateMachine

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_ROVER", "rover-control")
MQTT_PASS = os.getenv("MQTT_PASS_ROVER", "")

ROVER_ID = os.getenv("ROVER_ID", "field-rover-001")
ROVER_ASSET_ID = f"asset:robot:rover:{ROVER_ID}"

_rover = RoverMissionStateMachine(ROVER_ID)


async def _update_orchestrator_job_state(job_id: str, outcome: str) -> None:
    """Notify orchestrator of mission progress."""
    if not job_id:
        return
    try:
        action = "abort" if outcome in ("FAILED", "ABORTED") else None
        if not action:
            return
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/jobs/{job_id}/abort",
                params={"reason": f"Rover mission: {outcome}"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("orchestrator_update_failed", error=str(e))


async def _update_digital_twin() -> None:
    """Sync rover state to digital-twin."""
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{ROVER_ASSET_ID}/state",
                json={
                    "state": {
                        "value": _rover.state.value,
                        "battery_soc": _rover.battery_soc_pct,
                        "position": _rover.last_position,
                        "job_id": _rover.current_job_id,
                    },
                    "source": "rover-control",
                },
                timeout=5.0,
            )
    except Exception:
        pass


async def _mqtt_command_listener() -> None:
    """
    Listen for approved rover commands dispatched by orchestrator.
    Topic: commands/rover/{rover_id}/mission
    """
    try:
        import aiomqtt
    except ImportError:
        logger.warning("aiomqtt_not_available_skipping_rover_commands")
        return

    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USER,
                password=MQTT_PASS,
            ) as client:
                await client.subscribe(f"commands/rover/{ROVER_ID}/#")
                logger.info("rover_command_listener_ready", rover_id=ROVER_ID)
                async for message in client.messages:
                    try:
                        topic = str(message.topic)
                        payload = json.loads(message.payload)
                        command_type = topic.split("/")[-1]
                        await _handle_command(command_type, payload)
                    except Exception as e:
                        logger.error("rover_command_error", error=str(e))
        except Exception as e:
            logger.warning("rover_mqtt_disconnected", error=str(e))
            await asyncio.sleep(10)


async def _handle_command(command_type: str, payload: dict) -> None:
    """Process a rover command from orchestrator."""
    logger.info("rover_command_received", command_type=command_type)

    if command_type == "e_stop":
        _rover.e_stop(payload.get("reason", "Remote E-stop"))
        await _update_digital_twin()
        return

    if command_type == "mission":
        job_id = payload.get("job_id")
        waypoints = payload.get("waypoints", [])
        if not waypoints:
            logger.error("mission_command_no_waypoints", job_id=job_id)
            return
        try:
            _rover.transition(MissionState.DISPATCHING, reason=f"job:{job_id}")
            _rover.current_job_id = job_id
            _rover.waypoints = waypoints
            _rover.current_waypoint_idx = 0
            _rover.transition(MissionState.NAVIGATING, reason="Mission dispatched to Nav2")
            await _update_digital_twin()
            logger.info("rover_mission_started", job_id=job_id, waypoints=len(waypoints))
        except Exception as e:
            logger.error("rover_mission_dispatch_failed", error=str(e))
            _rover.state = MissionState.FAULT


async def _comms_watchdog() -> None:
    """Check for comms timeout and trigger safe-stop if exceeded."""
    while True:
        await asyncio.sleep(5)
        if _rover.check_comms_timeout():
            _rover.e_stop("Communications timeout")
            await _update_digital_twin()
            await _update_orchestrator_job_state(_rover.current_job_id or "", "ABORTED")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("rover_control_starting", rover_id=ROVER_ID)
    cmd_task = asyncio.create_task(_mqtt_command_listener())
    watchdog_task = asyncio.create_task(_comms_watchdog())
    yield
    cmd_task.cancel()
    watchdog_task.cancel()


app = FastAPI(
    title="Rover Control",
    description="Rover mission management — bridges orchestrator to ROS2 Nav2",
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
        "service": "rover-control",
        "version": "0.1.0",
        "rover_id": ROVER_ID,
        "state": _rover.state,
    }


@app.get("/status", tags=["rover"])
async def get_status():
    return _rover.status()


@app.get("/mission-log", tags=["rover"])
async def get_mission_log(limit: int = 50):
    return _rover.mission_log[-limit:]


class TelemetryUpdate(BaseModel):
    lat: float
    lon: float
    heading: float | None = None
    battery_soc_pct: float | None = None
    speed_ms: float | None = None


@app.post("/telemetry", tags=["rover"])
async def update_telemetry(payload: TelemetryUpdate):
    """
    Receive rover telemetry (from ROS2 bridge or SITL).
    Updates position, checks battery, triggers RTH if needed.
    """
    _rover.update_position(payload.lat, payload.lon, payload.heading)

    if payload.battery_soc_pct is not None:
        should_rth = _rover.update_battery(payload.battery_soc_pct)
        if should_rth and _rover.current_job_id:
            # Propose RTH job to orchestrator
            logger.warning("battery_low_rth_triggered", soc=payload.battery_soc_pct)
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{ORCHESTRATOR_URL}/jobs",
                        json={
                            "type": "rover.mission.return_home",
                            "origin": "POLICY",
                            "target_asset_ids": [ROVER_ASSET_ID],
                            "risk_class": "HIGH",
                            "parameters": {"reason": f"battery_low:{payload.battery_soc_pct}%"},
                            "requested_by": "rover-control",
                        },
                        timeout=5.0,
                    )
            except Exception as e:
                logger.error("rth_job_proposal_failed", error=str(e))

    await _update_digital_twin()
    return _rover.status()


@app.post("/e-stop", tags=["rover"])
async def e_stop(reason: str = "Operator E-stop"):
    """Emergency stop the rover from any state."""
    _rover.e_stop(reason)
    await _update_digital_twin()
    return _rover.status()


@app.post("/clear-fault", tags=["rover"])
async def clear_fault(operator_id: str):
    """Operator clears SAFE_STOP or FAULT state."""
    try:
        _rover.clear_fault(operator_id)
        await _update_digital_twin()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _rover.status()
