"""
Incident queue — manages security incidents from detection to resolution.

Incidents are created from canonical events (from frigate-adapter, OSINT).
Each incident has a state machine: NEW → TRIAGED → ACKNOWLEDGED → RESOLVED | DISMISSED.

Key rules:
  - No autonomous physical response — security-monitor only informs and queues
  - All response actions go through orchestrator job proposals
  - Incidents are never auto-resolved without operator acknowledgment (unless DISMISSED)
  - Privacy: person detection events require operator review; no LPR without consent
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class IncidentState(str, Enum):
    NEW = "NEW"
    TRIAGED = "TRIAGED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


ALLOWED_TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.NEW: {IncidentState.TRIAGED, IncidentState.DISMISSED},
    IncidentState.TRIAGED: {IncidentState.ACKNOWLEDGED, IncidentState.DISMISSED},
    IncidentState.ACKNOWLEDGED: {IncidentState.RESOLVED, IncidentState.DISMISSED},
    IncidentState.RESOLVED: set(),
    IncidentState.DISMISSED: set(),
}


class Incident:
    def __init__(
        self,
        event_id: str,
        event_type: str,
        asset_id: str,
        severity: IncidentSeverity,
        description: str,
        payload: dict[str, Any] | None = None,
    ):
        self.incident_id = str(uuid.uuid4())
        self.event_id = event_id
        self.event_type = event_type
        self.asset_id = asset_id
        self.severity = severity
        self.description = description
        self.payload = payload or {}
        self.state = IncidentState.NEW
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.acknowledged_by: str | None = None
        self.resolution_note: str | None = None
        self.triage_notes: list[str] = []
        self._log = logger.bind(incident_id=self.incident_id)

    def transition(self, target: IncidentState, *, actor: str | None = None, note: str | None = None) -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Cannot transition incident from {self.state} to {target}")
        prev = self.state
        self.state = target
        self.updated_at = datetime.utcnow()
        if actor:
            self.acknowledged_by = actor
        if note:
            self.triage_notes.append(f"[{datetime.utcnow().isoformat()}] {note}")
        if target in (IncidentState.RESOLVED, IncidentState.DISMISSED) and note:
            self.resolution_note = note
        self._log.info("incident_state_transition", from_state=prev, to_state=target, actor=actor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "asset_id": self.asset_id,
            "severity": self.severity,
            "description": self.description,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_by": self.acknowledged_by,
            "triage_notes": self.triage_notes,
            "resolution_note": self.resolution_note,
            "payload": self.payload,
        }


class IncidentQueue:
    """In-memory incident queue. Production: backed by Postgres."""

    def __init__(self):
        self._incidents: dict[str, Incident] = {}

    def create(self, canonical_event: dict) -> Incident:
        severity_map = {
            "INFO": IncidentSeverity.INFO,
            "WARNING": IncidentSeverity.WARNING,
            "CRITICAL": IncidentSeverity.CRITICAL,
        }
        severity = severity_map.get(canonical_event.get("severity", "INFO"), IncidentSeverity.INFO)

        event_type = canonical_event.get("event_type", "unknown")
        asset_id = canonical_event.get("asset_id", "unknown")
        label = canonical_event.get("payload", {}).get("label", "")

        description = f"{event_type} on {asset_id}"
        if label:
            description = f"{label} detected on {asset_id}"

        incident = Incident(
            event_id=canonical_event.get("event_id", str(uuid.uuid4())),
            event_type=event_type,
            asset_id=asset_id,
            severity=severity,
            description=description,
            payload=canonical_event.get("payload", {}),
        )

        # Auto-triage INFO severity events (not actionable without operator)
        if severity == IncidentSeverity.INFO:
            incident.transition(IncidentState.TRIAGED, note="Auto-triaged: INFO severity")

        self._incidents[incident.incident_id] = incident
        logger.info(
            "incident_created",
            incident_id=incident.incident_id,
            severity=severity,
            event_type=event_type,
        )
        return incident

    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def list_active(self) -> list[Incident]:
        return [
            i for i in self._incidents.values()
            if i.state not in (IncidentState.RESOLVED, IncidentState.DISMISSED)
        ]

    def list_all(self, limit: int = 100) -> list[Incident]:
        incidents = sorted(self._incidents.values(), key=lambda i: i.created_at, reverse=True)
        return incidents[:limit]
