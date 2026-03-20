"""
Home Assistant Adapter

Responsibilities (per ADR-003):
  - Subscribe to HA state changes via WebSocket (event: state_changed)
  - Translate vendor entity_id → canonical asset_id using entity_map
  - Publish canonical events to event-ingest via MQTT
  - Update digital-twin asset state
  - Execute commands from orchestrator on HA entities (write path)

What this adapter MUST NOT do:
  - Store job state (orchestrator owns jobs)
  - Make policy decisions
  - Be the system of record for asset state
  - Expose vendor entity_id to core services
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .entity_map import get_mapping, get_all_entity_ids

logger = structlog.get_logger(__name__)

HA_URL = os.getenv("HA_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_HA_ADAPTER", "ha-adapter")
MQTT_PASS = os.getenv("MQTT_PASS_HA_ADAPTER", "")

# Track adapter state
_connected_to_ha = False
_synced_entity_count = 0


async def _publish_canonical_event(asset_id: str, event_type: str, payload: dict) -> None:
    """Publish a canonical event to MQTT for event-ingest to consume."""
    try:
        import aiomqtt
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source_service": "ha-adapter",
            "asset_id": asset_id,
            "timestamp": datetime.utcnow().isoformat(),
            "severity": "INFO",
            "payload": payload,
        }
        async with aiomqtt.Client(
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASS,
        ) as client:
            await client.publish(
                f"events/{asset_id.replace(':', '/')}/{event_type}",
                payload=json.dumps(event),
            )
    except Exception as e:
        logger.warning("canonical_event_publish_failed", error=str(e))


async def _update_digital_twin_state(asset_id: str, state: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{asset_id}/state",
                json={"state": state, "source": "ha-adapter"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("digital_twin_update_failed", asset_id=asset_id, error=str(e))


async def _process_state_change(entity_id: str, new_state: str, attributes: dict) -> None:
    """Process a HA state_changed event."""
    mapping = get_mapping(entity_id)
    if not mapping:
        return  # Entity not in our map; ignore

    canonical_state = mapping.to_canonical_state(new_state, attributes)
    canonical_state["last_updated"] = datetime.utcnow().isoformat()

    # Update digital-twin
    await _update_digital_twin_state(mapping.asset_id, canonical_state)

    # Publish canonical event
    await _publish_canonical_event(
        asset_id=mapping.asset_id,
        event_type=mapping.event_type,
        payload={
            "state": canonical_state,
            "ha_entity_id": entity_id,  # Kept in payload for audit; not surfaced to core services
        },
    )

    logger.debug(
        "state_change_processed",
        entity_id=entity_id,
        asset_id=mapping.asset_id,
        state=canonical_state,
    )


async def _ha_websocket_listener() -> None:
    """
    Listen to Home Assistant WebSocket API for state change events.
    Automatically reconnects on disconnect.
    """
    global _connected_to_ha, _synced_entity_count

    if not HA_TOKEN:
        logger.warning("ha_token_not_set_skipping_websocket")
        return

    try:
        import websockets
    except ImportError:
        logger.warning("websockets_not_available_skipping_ha_listener")
        return

    ws_url = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                # HA auth handshake
                auth_required = json.loads(await ws.recv())
                if auth_required.get("type") == "auth_required":
                    await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
                    auth_result = json.loads(await ws.recv())
                    if auth_result.get("type") != "auth_ok":
                        logger.error("ha_auth_failed")
                        return

                _connected_to_ha = True
                logger.info("ha_websocket_connected", url=ws_url)

                # Subscribe to state change events
                await ws.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                }))

                # Do initial state sync
                await ws.send(json.dumps({"id": 2, "type": "get_states"}))

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        msg_type = msg.get("type")

                        if msg_type == "event":
                            event_data = msg.get("event", {}).get("data", {})
                            entity_id = event_data.get("entity_id")
                            new_state_data = event_data.get("new_state") or {}
                            if entity_id:
                                await _process_state_change(
                                    entity_id=entity_id,
                                    new_state=new_state_data.get("state", "unknown"),
                                    attributes=new_state_data.get("attributes", {}),
                                )

                        elif msg_type == "result" and msg.get("id") == 2:
                            # Initial state sync
                            states = msg.get("result") or []
                            for state_obj in states:
                                entity_id = state_obj.get("entity_id")
                                if entity_id and get_mapping(entity_id):
                                    await _process_state_change(
                                        entity_id=entity_id,
                                        new_state=state_obj.get("state", "unknown"),
                                        attributes=state_obj.get("attributes", {}),
                                    )
                                    _synced_entity_count += 1
                            logger.info("ha_initial_sync_complete", entities_synced=_synced_entity_count)

                    except Exception as e:
                        logger.error("ha_message_processing_error", error=str(e))

        except Exception as e:
            _connected_to_ha = False
            logger.warning("ha_websocket_disconnected", error=str(e))
            await asyncio.sleep(10)  # Reconnect delay


async def _execute_ha_command(entity_id: str, service: str, service_data: dict) -> bool:
    """
    Execute a command in HA via REST API.
    Called by the command webhook — only when orchestrator dispatches an approved command.
    """
    if not HA_TOKEN:
        return False
    try:
        domain = service.split(".")[0]
        service_name = service.split(".")[1]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{HA_URL}/api/services/{domain}/{service_name}",
                headers={"Authorization": f"Bearer {HA_TOKEN}"},
                json={"entity_id": entity_id, **service_data},
                timeout=10.0,
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error("ha_command_execution_failed", entity_id=entity_id, error=str(e))
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ha_adapter_starting")
    task = asyncio.create_task(_ha_websocket_listener())
    yield
    task.cancel()
    logger.info("ha_adapter_stopping")


app = FastAPI(
    title="HA Adapter",
    description="Home Assistant integration — state sync and command execution",
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
        "status": "ok" if _connected_to_ha else "degraded",
        "service": "ha-adapter",
        "version": "0.1.0",
        "ha_connected": _connected_to_ha,
        "entities_mapped": len(get_all_entity_ids()),
        "entities_synced": _synced_entity_count,
    }


class CommandWebhook(BaseModel):
    command_id: str
    job_id: str
    asset_id: str
    action: str
    parameters: dict = {}


@app.post("/commands", tags=["commands"])
async def execute_command(cmd: CommandWebhook):
    """
    Execute a command on a HA entity.
    Called by orchestrator after job approval.
    Maps canonical asset_id + action → HA entity_id + service call.
    """
    # Resolve vendor entity from digital-twin
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{DIGITAL_TWIN_URL}/assets/{cmd.asset_id}/resolve",
                timeout=5.0,
            )
            if resp.status_code != 200:
                return {"success": False, "error": "Asset not found in digital-twin"}
            resolution = resp.json()
            vendor_entity = resolution.get("vendor_entity")
    except Exception as e:
        return {"success": False, "error": str(e)}

    if not vendor_entity or vendor_entity.get("platform") != "home_assistant":
        return {"success": False, "error": "No HA vendor entity mapping for this asset"}

    entity_id = vendor_entity.get("entity_id")
    if not entity_id:
        return {"success": False, "error": "No entity_id in vendor_entity"}

    # Map action → HA service
    service_map = {
        "control:open": "switch.turn_on",
        "control:close": "switch.turn_off",
        "control:enable": "switch.turn_on",
        "control:disable": "switch.turn_off",
        "control:on": "switch.turn_on",
        "control:off": "switch.turn_off",
    }
    service = service_map.get(cmd.action)
    if not service:
        return {"success": False, "error": f"Unknown action: {cmd.action}"}

    success = await _execute_ha_command(entity_id, service, cmd.parameters)
    logger.info(
        "ha_command_executed",
        command_id=cmd.command_id,
        job_id=cmd.job_id,
        entity_id=entity_id,
        action=cmd.action,
        success=success,
    )
    return {"success": success, "entity_id": entity_id, "service": service}
