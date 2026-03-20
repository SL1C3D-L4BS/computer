"""
Hydroponics Control Service

Responsibilities:
  - Subscribe to pH, EC, temperature MQTT telemetry
  - Evaluate dosing thresholds
  - Propose nutrient/pH dosing jobs to orchestrator
  - Update digital-twin with sensor readings
  - Enforce dose interval safety rules

Must NOT:
  - Publish to command MQTT topics directly
  - Actuate peristaltic pumps without orchestrator job approval
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .state_machine import BayState, BayStateMachine

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

_bays: dict[str, BayStateMachine] = {}

# Default crop targets (should load from site config per bay)
_PH_TARGET = float(os.getenv("HYDRO_PH_TARGET", "6.0"))
_PH_TOLERANCE = float(os.getenv("HYDRO_PH_TOLERANCE", "0.3"))
_EC_TARGET_MS = float(os.getenv("HYDRO_EC_TARGET_MS", "1.6"))
_EC_TOLERANCE = float(os.getenv("HYDRO_EC_TOLERANCE", "0.2"))


def _get_or_create_bay(bay_id: str) -> BayStateMachine:
    if bay_id not in _bays:
        _bays[bay_id] = BayStateMachine(bay_id)
        _bays[bay_id].transition(BayState.MONITORING, reason="Service startup")
    return _bays[bay_id]


async def _propose_job(job_type: str, bay_id: str, parameters: dict, risk_class: str = "MEDIUM") -> str | None:
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
                    "requested_by": "hydro-control",
                },
                headers={"X-Service-ID": "hydro-control"},
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                logger.info("job_proposed", job_id=job["job_id"], job_type=job_type, bay_id=bay_id)
                return job["job_id"]
    except Exception as e:
        logger.error("job_proposal_failed", job_type=job_type, bay_id=bay_id, error=str(e))
    return None


async def _update_digital_twin_state(asset_id: str, state: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{asset_id}/state",
                json={"state": state, "source": "hydro-control"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("digital_twin_update_failed", asset_id=asset_id, error=str(e))


async def _process_telemetry(bay_id: str, readings: dict) -> None:
    bay = _get_or_create_bay(bay_id)
    bay.update_reading(readings)

    # Update digital-twin
    if "ph" in readings:
        await _update_digital_twin_state(
            f"asset:sensor:ph:{bay_id}",
            {"value": readings["ph"], "unit": "pH"},
        )
    if "ec_ms" in readings:
        await _update_digital_twin_state(
            f"asset:sensor:ec:{bay_id}",
            {"value": readings["ec_ms"], "unit": "mS/cm"},
        )

    if bay.state == BayState.SAFE_HOLD or bay.state in (BayState.DOSING_NUTRIENTS, BayState.ADJUSTING_PH):
        return

    # Evaluate pH adjustment need first (higher priority)
    ph_need = bay.evaluate_ph_need(target_ph=_PH_TARGET, tolerance=_PH_TOLERANCE)
    if ph_need:
        can_adjust, reason = bay.can_adjust_ph()
        if can_adjust:
            direction = ph_need["direction"]
            pump_id = (
                f"asset:actuator:pump:ph-up:{bay_id}"
                if direction == "up"
                else f"asset:actuator:pump:ph-down:{bay_id}"
            )
            job_id = await _propose_job(
                job_type=f"hydro.ph.adjust.{direction}",
                bay_id=bay_id,
                parameters={
                    "bay_id": bay_id,
                    "target_asset_ids": [pump_id],
                    "direction": direction,
                    "current_ph": ph_need["current_ph"],
                    "target_ph": ph_need["target_ph"],
                    "dose_ml": 2.0,  # Conservative default; policy may override
                },
                risk_class="MEDIUM",
            )
            if job_id:
                bay.pending_job_id = job_id
                bay.record_ph_adjust()
        else:
            logger.debug("ph_adjust_skipped", bay_id=bay_id, reason=reason)
        return  # Don't also dose nutrients in same cycle

    # Evaluate nutrient need
    if bay.evaluate_nutrient_need(target_ec_ms=_EC_TARGET_MS, tolerance=_EC_TOLERANCE):
        can_dose, reason = bay.can_dose()
        if can_dose:
            job_id = await _propose_job(
                job_type="hydro.nutrients.dose",
                bay_id=bay_id,
                parameters={
                    "bay_id": bay_id,
                    "target_asset_ids": [
                        f"asset:actuator:pump:nutrient:{bay_id}-a",
                        f"asset:actuator:pump:nutrient:{bay_id}-b",
                    ],
                    "current_ec_ms": readings.get("ec_ms"),
                    "target_ec_ms": _EC_TARGET_MS,
                    "dose_ml_a": 5.0,
                    "dose_ml_b": 5.0,
                },
                risk_class="MEDIUM",
            )
            if job_id:
                bay.pending_job_id = job_id
                bay.record_dose()
        else:
            logger.debug("nutrient_dose_skipped", bay_id=bay_id, reason=reason)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("hydro_control_starting")
    _get_or_create_bay("hydro-bay-1")
    yield
    logger.info("hydro_control_stopping")


app = FastAPI(
    title="Hydro Control",
    description="Hydroponics management — pH/EC monitoring and dosing job proposals",
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
    return {"status": "ok", "service": "hydro-control", "version": "0.1.0", "bays": len(_bays)}


@app.get("/bays", tags=["bays"])
async def list_bays():
    return [bay.status() for bay in _bays.values()]


@app.get("/bays/{bay_id}", tags=["bays"])
async def get_bay(bay_id: str):
    if bay_id not in _bays:
        raise HTTPException(status_code=404, detail=f"Bay {bay_id} not found")
    return _bays[bay_id].status()


class TelemetryPayload(BaseModel):
    ph: float | None = None
    ec_ms: float | None = None
    water_temp_celsius: float | None = None
    do_mg_l: float | None = None


@app.post("/bays/{bay_id}/telemetry", tags=["bays"])
async def inject_telemetry(bay_id: str, payload: TelemetryPayload):
    """Inject telemetry for testing/simulation. Production: MQTT."""
    readings = {k: v for k, v in payload.model_dump().items() if v is not None}
    await _process_telemetry(bay_id, readings)
    return _get_or_create_bay(bay_id).status()
