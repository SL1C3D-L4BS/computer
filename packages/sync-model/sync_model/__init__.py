"""
Sync Model — Local-First Sync for family-web

CRDT-compatible conflict types and sync operation primitives.
Enables family-web to function offline and sync on reconnect.

Reference: docs/architecture/missing-runtime-planes.md (Local-First Sync section)
ADR: ADR-021 (Local-First Sync Plane)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CRDTOperation:
    """A CRDT-compatible state operation."""
    type: str           # "set" | "delete" | "increment" | "append"
    field_path: str     # Dot-notation path: "shopping_list.items"
    value: Any
    vector_clock: dict[str, int]  # Lamport-style vector clock
    actor_id: str       # User or device that produced this operation
    timestamp_ms: int   # Wall clock (informational only — use vector_clock for ordering)


@dataclass
class SyncConflict:
    """A detected conflict between local and remote state."""
    local_op: CRDTOperation
    remote_op: CRDTOperation
    field_path: str
    resolution: str = "last_write_wins"  # "last_write_wins" | "merge" | "user_prompt"


@dataclass
class SyncQueue:
    """Pending operations not yet synced to the server."""
    actor_id: str
    operations: list[CRDTOperation] = field(default_factory=list)
    last_sync_ms: int = 0

    def enqueue(self, op: CRDTOperation) -> None:
        self.operations.append(op)

    def flush(self) -> list[CRDTOperation]:
        ops = list(self.operations)
        self.operations.clear()
        return ops
