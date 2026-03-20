"""
Frigate event normalizer.

Translates Frigate MQTT detection events into canonical CanonicalEvent format.
The only place where Frigate camera names appear; core services see asset_ids only.

Frigate MQTT topics:
  frigate/events            — new/update/end detection events
  frigate/{camera}/motion   — motion state changes
  frigate/{camera}/person   — person detection counts
  frigate/{camera}/car      — vehicle detection counts
  frigate/reviews           — review notifications

See ADR-008 (OSINT optional), ADR-003 (HA not system of record).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


# Camera name → canonical asset_id mapping
# Only adapter layer touches Frigate camera names (same pattern as HA entity map)
CAMERA_MAP: dict[str, str] = {
    "exterior_north": "asset:sensor:camera:exterior-north",
    "greenhouse_north": "asset:sensor:camera:greenhouse-north",
    "driveway": "asset:sensor:camera:driveway",
}


def camera_to_asset_id(camera_name: str) -> str | None:
    return CAMERA_MAP.get(camera_name)


def normalize_frigate_event(raw_event: dict) -> dict | None:
    """
    Convert a Frigate event dict to a CanonicalEvent dict.
    Returns None if event should be ignored or cannot be mapped.
    """
    camera = raw_event.get("camera")
    asset_id = camera_to_asset_id(camera or "")
    if not asset_id:
        return None  # Unknown camera; ignore

    event_type_map = {
        "new": "security.detection.new",
        "update": "security.detection.updated",
        "end": "security.detection.ended",
    }
    frigate_type = raw_event.get("type", "new")
    event_type = event_type_map.get(frigate_type, "security.detection.new")

    label = raw_event.get("label", "unknown")
    score = raw_event.get("score", 0.0)
    top_score = raw_event.get("top_score", score)
    has_clip = raw_event.get("has_clip", False)
    has_snapshot = raw_event.get("has_snapshot", False)

    # Severity based on label
    severity_map = {
        "person": "WARNING",
        "car": "INFO",
        "cat": "INFO",
        "dog": "INFO",
        "fire": "CRITICAL",
        "smoke": "CRITICAL",
    }
    severity = severity_map.get(label.lower(), "INFO")

    return {
        "event_id": raw_event.get("id") or str(uuid.uuid4()),
        "event_type": event_type,
        "source_service": "frigate-adapter",
        "asset_id": asset_id,
        "timestamp": datetime.utcnow().isoformat(),
        "severity": severity,
        "payload": {
            "label": label,
            "score": score,
            "top_score": top_score,
            "camera": camera,  # Kept in payload for audit; never used by core services
            "frigate_event_id": raw_event.get("id"),
            "has_clip": has_clip,
            "has_snapshot": has_snapshot,
            "zones": raw_event.get("current_zones", []),
            "entered_zones": raw_event.get("entered_zones", []),
            "thumbnail": raw_event.get("thumbnail"),
        },
    }


def normalize_frigate_motion(camera: str, motion_state: str) -> dict | None:
    """Normalize a Frigate motion state change event."""
    asset_id = camera_to_asset_id(camera)
    if not asset_id:
        return None

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "security.motion.detected" if motion_state == "1" else "security.motion.cleared",
        "source_service": "frigate-adapter",
        "asset_id": asset_id,
        "timestamp": datetime.utcnow().isoformat(),
        "severity": "INFO",
        "payload": {
            "camera": camera,
            "motion_active": motion_state == "1",
        },
    }
