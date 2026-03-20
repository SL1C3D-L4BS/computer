"""
Energy Engine Service

Responsibilities:
  - Monitor grid, solar, and battery telemetry
  - Evaluate TOU peak/off-peak windows
  - Propose battery dispatch jobs to orchestrator
  - Expose energy state and telemetry endpoints
  - Track TOU rate for advisory/forecasting

Must NOT:
  - Directly control inverters, batteries, or grid switches
  - Publish to command MQTT topics
  - Make high-risk decisions without orchestrator approval
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .state_machine import EnergyState, EnergyStateMachine

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")

_engine = EnergyStateMachine()

# TOU config (should load from site config SDK)
_PEAK_SHAVE_TARGET_KW = float(os.getenv("PEAK_SHAVE_TARGET_KW", "5.0"))
_GRID_CHARGE_THRESHOLD_SOC = float(os.getenv("GRID_CHARGE_THRESHOLD_SOC", "20.0"))
_DISCHARGE_RESERVE_SOC = float(os.getenv("DISCHARGE_RESERVE_SOC", "15.0"))
_TOU_PEAK_START_HOUR = int(os.getenv("TOU_PEAK_START_HOUR", "7"))
_TOU_PEAK_END_HOUR = int(os.getenv("TOU_PEAK_END_HOUR", "21"))


def _is_tou_peak() -> bool:
    now = datetime.now(timezone.utc)
    # Simplified: weekday 7am-9pm Pacific (UTC-7 or UTC-8)
    local_hour = (now.hour - 7) % 24  # Approximate Pacific time
    is_weekday = now.weekday() < 5
    return is_weekday and _TOU_PEAK_START_HOUR <= local_hour < _TOU_PEAK_END_HOUR


async def _propose_job(job_type: str, parameters: dict, risk_class: str = "MEDIUM") -> str | None:
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
                    "requested_by": "energy-engine",
                },
                headers={"X-Service-ID": "energy-engine"},
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                logger.info("energy_job_proposed", job_id=job["job_id"], job_type=job_type)
                return job["job_id"]
    except Exception as e:
        logger.error("energy_job_proposal_failed", job_type=job_type, error=str(e))
    return None


async def _update_digital_twin_state(asset_id: str, state: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{asset_id}/state",
                json={"state": state, "source": "energy-engine"},
                timeout=5.0,
            )
    except Exception:
        pass


async def _evaluate_energy_dispatch() -> None:
    """Core energy dispatch logic — evaluate and propose jobs as needed."""
    is_peak = _is_tou_peak()
    is_off_peak = not is_peak

    # Peak shaving opportunity
    if (
        _engine.state == EnergyState.NORMAL
        and _engine.evaluate_peak_shave_opportunity(
            peak_shave_target_kw=_PEAK_SHAVE_TARGET_KW,
            discharge_reserve_soc_pct=_DISCHARGE_RESERVE_SOC,
            is_tou_peak=is_peak,
        )
    ):
        job_id = await _propose_job(
            job_type="energy.battery.discharge",
            parameters={
                "target_asset_ids": [
                    "asset:storage:battery:bluetti-ac300-1",
                    "asset:storage:battery:bluetti-ac300-2",
                ],
                "target_kw": _PEAK_SHAVE_TARGET_KW,
                "reason": "tou_peak_shaving",
                "current_grid_kw": _engine.last_grid_kw,
                "battery_soc_pct": _engine.last_battery_soc_pct,
            },
            risk_class="MEDIUM",
        )
        if job_id:
            _engine.transition(EnergyState.PEAK_SHAVING, reason="TOU peak + excess grid import")

    # Off-peak grid charging
    elif (
        _engine.state == EnergyState.NORMAL
        and _engine.evaluate_grid_charge_opportunity(
            grid_charge_threshold_soc_pct=_GRID_CHARGE_THRESHOLD_SOC,
            is_tou_off_peak=is_off_peak,
        )
    ):
        job_id = await _propose_job(
            job_type="energy.battery.grid_charge",
            parameters={
                "target_asset_ids": [
                    "asset:storage:battery:bluetti-ac300-1",
                    "asset:storage:battery:bluetti-ac300-2",
                ],
                "target_soc_pct": 80,
                "reason": "off_peak_grid_charge",
                "current_soc_pct": _engine.last_battery_soc_pct,
            },
            risk_class="MEDIUM",
        )
        if job_id:
            _engine.transition(EnergyState.GRID_CHARGING, reason="Off-peak SOC below threshold")

    # Return to NORMAL from PEAK_SHAVING when peak window ends
    elif _engine.state == EnergyState.PEAK_SHAVING and not is_peak:
        _engine.transition(EnergyState.NORMAL, reason="TOU peak window ended")

    # Return to NORMAL from GRID_CHARGING when battery is charged
    elif (
        _engine.state == EnergyState.GRID_CHARGING
        and _engine.last_battery_soc_pct is not None
        and _engine.last_battery_soc_pct >= 80
    ):
        _engine.transition(EnergyState.NORMAL, reason="Battery charged to target SOC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("energy_engine_starting")
    yield
    logger.info("energy_engine_stopping")


app = FastAPI(
    title="Energy Engine",
    description="TOU optimization, solar forecasting, and battery dispatch proposals",
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
        "service": "energy-engine",
        "version": "0.1.0",
        "energy_state": _engine.state,
    }


@app.get("/status", tags=["energy"])
async def get_status():
    """Current energy state and latest readings."""
    return {
        **_engine.status(),
        "is_tou_peak": _is_tou_peak(),
    }


class EnergyTelemetry(BaseModel):
    grid_import_kw: float | None = None
    solar_production_kw: float | None = None
    battery_soc_pct: float | None = None


@app.post("/telemetry", tags=["energy"])
async def inject_telemetry(payload: EnergyTelemetry):
    """Inject energy telemetry. Production: from MQTT/HA adapter."""
    _engine.update_readings(
        grid_kw=payload.grid_import_kw,
        solar_kw=payload.solar_production_kw,
        battery_soc_pct=payload.battery_soc_pct,
    )

    # Update digital-twin
    if payload.grid_import_kw is not None:
        await _update_digital_twin_state(
            "asset:sensor:energy:grid-meter",
            {"value": payload.grid_import_kw, "unit": "kW"},
        )
    if payload.solar_production_kw is not None:
        await _update_digital_twin_state(
            "asset:sensor:energy:solar-production",
            {"value": payload.solar_production_kw, "unit": "kW"},
        )

    # Evaluate dispatch
    await _evaluate_energy_dispatch()
    return _engine.status()
