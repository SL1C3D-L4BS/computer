"""
Event Ingest — MQTT subscriber, event normalizer, canonical event writer.

Rules:
- Subscribes to MQTT telemetry and event topics
- Normalizes to canonical event schema (packages/contracts/event.schema.json)
- Writes to Postgres events table
- Optionally notifies orchestrator for sensor_rule-driven job creation
- NEVER publishes to command_request topics
- NEVER actuates hardware
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

# In-memory event buffer for development; replace with Postgres
_events: list[dict] = []


class CanonicalEvent(BaseModel):
    event_id: str
    event_type: str
    source_service: str
    asset_id: str
    zone: str | None = None
    severity: str = "INFO"
    timestamp: datetime
    ingested_at: datetime
    payload: dict
    request_id: str | None = None
    job_id: str | None = None


def normalize_telemetry(mqtt_topic: str, raw_payload: dict) -> CanonicalEvent | None:
    """
    Normalize a raw MQTT telemetry payload to canonical event format.
    Topic format: computer/{site}/{domain}/{asset_id}/telemetry
    """
    parts = mqtt_topic.split("/")
    if len(parts) < 5:
        return None

    asset_id_from_topic = parts[3]
    channel = parts[4]

    event_type_map = {
        "telemetry": "TELEMETRY",
        "event": "SENSOR_ALERT",
        "health": "SYSTEM_HEALTH",
    }

    return CanonicalEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type_map.get(channel, "TELEMETRY"),
        source_service="event-ingest",
        asset_id=raw_payload.get("asset_id", asset_id_from_topic),
        zone=raw_payload.get("zone"),
        severity=raw_payload.get("severity", "INFO"),
        timestamp=datetime.fromisoformat(raw_payload["timestamp"])
        if "timestamp" in raw_payload
        else datetime.utcnow(),
        ingested_at=datetime.utcnow(),
        payload=raw_payload,
    )


async def mqtt_subscriber():
    """
    Subscribe to MQTT topics and normalize events.
    Uses aiomqtt. Reconnects on failure per degraded-mode-spec.
    """
    topic_prefix = "computer/#"
    logger.info("mqtt_subscriber_starting", host=MQTT_HOST, port=MQTT_PORT)

    while True:
        try:
            import aiomqtt
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                identifier=f"event-ingest-{uuid.uuid4().hex[:8]}",
            ) as client:
                await client.subscribe(topic_prefix)
                logger.info("mqtt_subscribed", topic=topic_prefix)

                async for message in client.messages:
                    topic = str(message.topic)
                    # Skip command topics — event-ingest never reads commands
                    if "command_request" in topic or "command_ack" in topic:
                        continue
                    try:
                        import json
                        payload = json.loads(message.payload)
                        event = normalize_telemetry(topic, payload)
                        if event:
                            _events.append(event.model_dump())
                            logger.debug("event_ingested", event_id=event.event_id, type=event.event_type)
                    except Exception as e:
                        logger.warning("event_normalization_failed", topic=topic, error=str(e))
        except Exception as e:
            logger.warning("mqtt_disconnected", error=str(e))
            await asyncio.sleep(5)  # Retry after 5 seconds per degraded-mode-spec


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(mqtt_subscriber())
    yield
    task.cancel()


app = FastAPI(
    title="Computer Event Ingest",
    description="MQTT subscriber, event normalizer, canonical event writer",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "event-ingest",
        "version": "0.1.0",
        "events_buffered": len(_events),
    }


@app.get("/events", tags=["events"])
async def list_events(
    asset_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
):
    """List recent events."""
    events = list(reversed(_events))
    if asset_id:
        events = [e for e in events if e.get("asset_id") == asset_id]
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    return events[:limit]
