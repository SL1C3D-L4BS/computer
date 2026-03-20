"""
Operator copilot tools.

Each tool either:
  1. Reads data (INFORMATIONAL/LOW — no approval needed)
  2. Proposes a job to orchestrator via AI_ADVISORY origin (MEDIUM/HIGH — requires approval)

NEVER:
  - Publish to MQTT directly (CI gate F01 catches this)
  - Call HA or control services directly
  - Auto-approve any job

The propose_job tool is the ONLY way AI can trigger physical actions.
It submits to orchestrator with origin=AI_ADVISORY, which requires
OPERATOR_REQUIRED approval for MEDIUM+ risk (F05 enforced).
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from .tool_registry import ToolDefinition, ToolRiskClass, register_tool

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")


# ── Read tools (INFORMATIONAL) ────────────────────────────────────────────────

async def _get_asset_state(asset_id: str) -> dict[str, Any]:
    """Read current state of an asset from digital-twin."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DIGITAL_TWIN_URL}/assets/{asset_id}", timeout=5.0)
            if resp.status_code == 404:
                return {"error": f"Asset {asset_id} not found"}
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


register_tool(
    ToolDefinition(
        name="get_asset_state",
        description="Read the current state of a site asset (sensor reading, actuator status, battery SOC, etc.)",
        risk_class=ToolRiskClass.INFORMATIONAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Canonical asset ID (e.g. asset:sensor:temp:greenhouse-north)",
                },
            },
            "required": ["asset_id"],
        },
    ),
    _get_asset_state,
)


async def _list_assets(zone: str | None = None, asset_type: str | None = None) -> dict[str, Any]:
    """List assets in the digital twin."""
    try:
        params = {}
        if zone:
            params["zone"] = zone
        if asset_type:
            params["asset_type"] = asset_type
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DIGITAL_TWIN_URL}/assets", params=params, timeout=5.0)
            return {"assets": resp.json(), "count": len(resp.json())}
    except Exception as e:
        return {"error": str(e)}


register_tool(
    ToolDefinition(
        name="list_assets",
        description="List assets in the site digital twin, optionally filtered by zone or type",
        risk_class=ToolRiskClass.INFORMATIONAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "zone": {"type": "string", "description": "Filter by zone ID"},
                "asset_type": {"type": "string", "description": "Filter by asset type"},
            },
        },
    ),
    _list_assets,
)


async def _list_recent_jobs(
    state: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """List recent jobs from the orchestrator."""
    try:
        params = {"limit": limit}
        if state:
            params["state"] = state
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{ORCHESTRATOR_URL}/jobs", params=params, timeout=5.0)
            return {"jobs": resp.json()}
    except Exception as e:
        return {"error": str(e)}


register_tool(
    ToolDefinition(
        name="list_recent_jobs",
        description="List recent jobs from the orchestrator with optional state filter",
        risk_class=ToolRiskClass.INFORMATIONAL,
        parameters_schema={
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Filter by job state (PENDING, VALIDATING, APPROVED, EXECUTING, COMPLETED, FAILED, ABORTED)",
                },
                "limit": {"type": "integer", "default": 10},
            },
        },
    ),
    _list_recent_jobs,
)


# ── Action tools (AI_ADVISORY — route through orchestrator) ───────────────────

async def _propose_irrigation_job(
    zone_id: str,
    duration_minutes: int,
    reason: str,
) -> dict[str, Any]:
    """
    Propose an irrigation job for operator approval.
    NEVER auto-executes — requires OPERATOR_REQUIRED approval.
    """
    valve_map = {
        "zone-1": "asset:actuator:valve:irrigation:zone-1",
        "zone-2": "asset:actuator:valve:irrigation:zone-2",
        "greenhouse-north": "asset:actuator:valve:irrigation:greenhouse-north",
        "greenhouse-south": "asset:actuator:valve:irrigation:greenhouse-south",
    }
    valve_id = valve_map.get(zone_id)
    if not valve_id:
        return {"error": f"Unknown irrigation zone: {zone_id}"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs",
                json={
                    "type": "irrigation.zone.enable",
                    "origin": "AI_ADVISORY",
                    "target_asset_ids": [valve_id],
                    "risk_class": "HIGH",
                    "parameters": {
                        "zone_id": zone_id,
                        "duration_minutes": duration_minutes,
                        "reason": reason,
                    },
                    "requested_by": "model-router",
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                return {
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "approval_mode": job["approval_mode"],
                    "message": f"Irrigation job proposed for operator approval. Job ID: {job['job_id']}",
                }
            return {"error": f"Failed to submit job: {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


register_tool(
    ToolDefinition(
        name="propose_irrigation",
        description="Propose an irrigation job for a specific zone. REQUIRES OPERATOR APPROVAL before execution.",
        risk_class=ToolRiskClass.HIGH,
        requires_operator_confirmation=True,
        parameters_schema={
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "enum": ["zone-1", "zone-2", "greenhouse-north", "greenhouse-south"],
                    "description": "Irrigation zone to water",
                },
                "duration_minutes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 120,
                    "description": "Duration in minutes",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for irrigation (e.g. 'soil moisture below 40% VWC')",
                },
            },
            "required": ["zone_id", "duration_minutes", "reason"],
        },
    ),
    _propose_irrigation_job,
)


async def _propose_sensor_read(
    asset_id: str,
    reading_type: str,
) -> dict[str, Any]:
    """Propose a sensor read job (LOW risk — auto-approved)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs",
                json={
                    "type": "sensor.read",
                    "origin": "AI_ADVISORY",
                    "target_asset_ids": [asset_id],
                    "risk_class": "LOW",
                    "parameters": {"reading_type": reading_type},
                    "requested_by": "model-router",
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                return {"job_id": job["job_id"], "state": job["state"]}
            return {"error": f"Failed: {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


register_tool(
    ToolDefinition(
        name="read_sensor",
        description="Request a sensor reading for a specific asset. Low-risk, auto-approved.",
        risk_class=ToolRiskClass.LOW,
        parameters_schema={
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Canonical asset ID"},
                "reading_type": {"type": "string", "description": "Type of reading (temperature, humidity, ph, ec, etc.)"},
            },
            "required": ["asset_id", "reading_type"],
        },
    ),
    _propose_sensor_read,
)
