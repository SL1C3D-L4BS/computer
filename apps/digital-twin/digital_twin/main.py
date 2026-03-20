"""
Digital Twin FastAPI service — asset registry and site entity definitions.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# In-memory asset store for development
_assets: dict[str, dict[str, Any]] = {}


class QualificationLevel(str, Enum):
    QA0 = "QA0"
    QA1 = "QA1"
    QA2 = "QA2"
    QA3 = "QA3"
    QA4 = "QA4"


class OperationalStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"
    E_STOPPED = "E_STOPPED"
    UNKNOWN = "UNKNOWN"


class AssetCreate(BaseModel):
    asset_id: str
    name: str
    asset_type: str
    capabilities: list[str] = []
    zone: str | None = None
    location_description: str | None = None
    current_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    qualification_level: QualificationLevel = QualificationLevel.QA0
    operational_status: OperationalStatus = OperationalStatus.UNKNOWN


class AssetStateUpdate(BaseModel):
    state: dict[str, Any]
    source: str
    timestamp: datetime | None = None


app = FastAPI(
    title="Computer Digital Twin",
    description="Asset registry and site entity definitions",
    version="0.1.0",
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
        "service": "digital-twin",
        "version": "0.1.0",
        "asset_count": len(_assets),
    }


@app.post("/assets", status_code=201, tags=["assets"])
async def create_asset(asset: AssetCreate):
    """Register a new asset in the digital twin."""
    if asset.asset_id in _assets:
        raise HTTPException(status_code=409, detail="Asset already exists")
    record = asset.model_dump()
    record["state"] = asset.current_state or {}
    record["state_updated_at"] = None
    record["created_at"] = datetime.utcnow().isoformat()
    record["updated_at"] = datetime.utcnow().isoformat()
    _assets[asset.asset_id] = record
    logger.info("asset_created", asset_id=asset.asset_id, asset_type=asset.asset_type)
    return record


@app.get("/assets", tags=["assets"])
async def list_assets(
    zone: str | None = None,
    asset_type: str | None = None,
    capability: str | None = None,
):
    """List assets with optional filters."""
    assets = list(_assets.values())
    if zone:
        assets = [a for a in assets if a.get("zone") == zone]
    if asset_type:
        assets = [a for a in assets if a.get("asset_type") == asset_type]
    if capability:
        assets = [a for a in assets if capability in a.get("capabilities", [])]
    return assets


@app.get("/assets/{asset_id}", tags=["assets"])
async def get_asset(asset_id: str):
    """Get a specific asset."""
    if asset_id not in _assets:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _assets[asset_id]


@app.patch("/assets/{asset_id}/state", tags=["assets"])
async def update_asset_state(asset_id: str, update: AssetStateUpdate):
    """
    Update asset state. Called by adapters (ha-adapter, control services).
    Never called by orchestrator or AI paths.
    """
    if asset_id not in _assets:
        raise HTTPException(status_code=404, detail="Asset not found")
    _assets[asset_id]["state"] = update.state
    _assets[asset_id]["state_source"] = update.source
    _assets[asset_id]["state_updated_at"] = (
        update.timestamp or datetime.utcnow()
    ).isoformat()
    _assets[asset_id]["updated_at"] = datetime.utcnow().isoformat()
    return _assets[asset_id]


@app.get("/assets/{asset_id}/resolve", tags=["assets"])
async def resolve_capability(asset_id: str):
    """
    Resolve an asset's vendor_entity for adapter use only.
    This endpoint is ONLY for adapters. Orchestrator must not call this.
    """
    if asset_id not in _assets:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset = _assets[asset_id]
    return {
        "asset_id": asset_id,
        "vendor_entity": asset.get("vendor_entity"),
        "mqtt_topic_prefix": asset.get("mqtt_topic_prefix"),
    }
