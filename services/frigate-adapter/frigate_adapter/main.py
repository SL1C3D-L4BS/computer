"""
Frigate Adapter Service

Responsibilities:
  - Subscribe to Frigate MQTT topics (frigate/events, frigate/{camera}/motion)
  - Normalize Frigate events to canonical CanonicalEvent format
  - Forward canonical events to event-ingest via MQTT
  - Update digital-twin camera asset state
  - Accept simulated event injection for testing

Must NOT:
  - Store detection history (event-ingest handles this)
  - Make access control decisions
  - Trigger any response actions (security-monitor handles incident triage)
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .event_normalizer import normalize_frigate_event, normalize_frigate_motion

logger = structlog.get_logger(__name__)

DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER_FRIGATE", "frigate-adapter")
MQTT_PASS = os.getenv("MQTT_PASS_FRIGATE", "")

_event_buffer: list[dict] = []
_MAX_BUFFER = 100


async def _publish_canonical_event(event: dict) -> None:
    """Forward canonical event to MQTT event bus."""
    try:
        import aiomqtt
        topic = f"events/canonical/{event['asset_id'].replace(':', '/')}"
        async with aiomqtt.Client(
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASS,
        ) as client:
            await client.publish(topic, payload=json.dumps(event))
    except Exception as e:
        logger.warning("event_publish_failed", error=str(e))


async def _update_digital_twin(asset_id: str, state: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{DIGITAL_TWIN_URL}/assets/{asset_id}/state",
                json={"state": state, "source": "frigate-adapter"},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("digital_twin_update_failed", asset_id=asset_id, error=str(e))


async def _process_frigate_event(raw: dict) -> None:
    """Process a Frigate detection event."""
    canonical = normalize_frigate_event(raw)
    if not canonical:
        return

    _event_buffer.append(canonical)
    if len(_event_buffer) > _MAX_BUFFER:
        _event_buffer.pop(0)

    # Update digital-twin camera state
    await _update_digital_twin(
        canonical["asset_id"],
        {
            "value": "detecting",
            "label": canonical["payload"].get("label"),
            "score": canonical["payload"].get("score"),
        },
    )

    await _publish_canonical_event(canonical)
    logger.info(
        "detection_event_normalized",
        asset_id=canonical["asset_id"],
        label=canonical["payload"].get("label"),
        severity=canonical["severity"],
    )


async def _mqtt_subscriber() -> None:
    """Subscribe to Frigate MQTT topics."""
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
                await client.subscribe("frigate/#")
                logger.info("frigate_mqtt_subscribed")
                async for message in client.messages:
                    try:
                        topic = str(message.topic)
                        payload = json.loads(message.payload)

                        if topic == "frigate/events":
                            await _process_frigate_event(payload)

                        elif "/motion" in topic:
                            # Topic: frigate/{camera}/motion, payload: "0" or "1"
                            parts = topic.split("/")
                            if len(parts) >= 3:
                                camera = parts[1]
                                motion = str(payload)
                                canonical = normalize_frigate_motion(camera, motion)
                                if canonical:
                                    await _publish_canonical_event(canonical)
                    except Exception as e:
                        logger.error("mqtt_message_error", error=str(e))
        except Exception as e:
            logger.warning("frigate_mqtt_disconnected", error=str(e))
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("frigate_adapter_starting")
    task = asyncio.create_task(_mqtt_subscriber())
    yield
    task.cancel()


app = FastAPI(
    title="Frigate Adapter",
    description="Frigate NVR adapter — normalizes security detection events",
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
        "service": "frigate-adapter",
        "version": "0.1.0",
        "buffered_events": len(_event_buffer),
    }


@app.get("/events", tags=["events"])
async def list_recent_events(limit: int = 20):
    """Return recent detection events from buffer."""
    return _event_buffer[-limit:]


class SimulatedDetection(BaseModel):
    camera: str
    label: str
    score: float = 0.85
    event_type: str = "new"
    current_zones: list[str] = []


@app.post("/events/simulate", tags=["events"])
async def simulate_detection(payload: SimulatedDetection):
    """Inject a simulated Frigate detection event for testing."""
    raw_event = {
        "type": payload.event_type,
        "camera": payload.camera,
        "label": payload.label,
        "score": payload.score,
        "top_score": payload.score,
        "current_zones": payload.current_zones,
        "has_clip": False,
        "has_snapshot": False,
    }
    await _process_frigate_event(raw_event)
    return {"simulated": True, "camera": payload.camera, "label": payload.label}
