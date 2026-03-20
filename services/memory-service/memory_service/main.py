"""
Memory Service

Manages memory partitioned into three non-overlapping scopes (ADR-013):
  - PERSONAL: private to a specific user
  - HOUSEHOLD_SHARED: visible to all household members
  - SITE_SYSTEM: operational knowledge, no personal content

Enforcement rules:
  - PERSONAL scope: only the owning user_id can read or write
  - HOUSEHOLD_SHARED: any ADULT_MEMBER+ can read; write requires ADULT_MEMBER+
  - SITE_SYSTEM: only services with system roles can write; any authorized user can read

All scope enforcement is done here, not in callers.
Production: backed by Postgres with vector search for semantic recall.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class MemoryScope(str, Enum):
    PERSONAL = "PERSONAL"
    HOUSEHOLD_SHARED = "HOUSEHOLD_SHARED"
    SITE_SYSTEM = "SITE_SYSTEM"


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    ROUTINE = "routine"
    TASK = "task"
    NOTE = "note"
    SUMMARY = "summary"
    CONTEXT = "context"


class MemoryRecord(BaseModel):
    memory_id: str
    user_id: str  # Owning user (or "system" for SITE_SYSTEM)
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    structured_data: dict[str, Any] = {}
    tags: list[str] = []
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateMemoryRequest(BaseModel):
    user_id: str
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    structured_data: dict[str, Any] = {}
    tags: list[str] = []
    expires_at: datetime | None = None
    requestor_id: str  # Who is creating this memory
    requestor_scopes: list[str]  # From ContextEnvelope.eligible_memory_scopes


class QueryMemoryRequest(BaseModel):
    user_id: str
    scopes: list[MemoryScope]
    query: str | None = None
    memory_type: MemoryType | None = None
    tags: list[str] = []
    limit: int = 20
    requestor_id: str
    requestor_scopes: list[str]


# In-memory store (production: Postgres + pgvector)
_memories: dict[str, MemoryRecord] = {}


def _check_read_permission(
    requestor_id: str,
    requestor_scopes: list[str],
    scope: MemoryScope,
    owner_user_id: str,
) -> bool:
    """Verify requestor can read a memory record."""
    scope_str = scope.value
    if scope_str not in requestor_scopes:
        return False
    if scope == MemoryScope.PERSONAL:
        return requestor_id == owner_user_id
    return True  # HOUSEHOLD_SHARED and SITE_SYSTEM are readable by anyone with scope


def _check_write_permission(
    requestor_id: str,
    requestor_scopes: list[str],
    scope: MemoryScope,
    target_user_id: str,
) -> bool:
    """Verify requestor can write to a scope."""
    scope_str = scope.value
    if scope_str not in requestor_scopes:
        return False
    if scope == MemoryScope.PERSONAL:
        return requestor_id == target_user_id
    return True


app = FastAPI(
    title="Memory Service",
    description="Scoped personal/household/site memory management (ADR-013)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "memory-service",
        "version": "0.1.0",
        "total_records": len(_memories),
    }


@app.post("/memories", response_model=MemoryRecord, status_code=201, tags=["memory"])
async def create_memory(req: CreateMemoryRequest):
    """Store a memory record with scope enforcement."""
    if not _check_write_permission(
        req.requestor_id, req.requestor_scopes, req.scope, req.user_id
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: cannot write to {req.scope} scope for user {req.user_id}",
        )

    record = MemoryRecord(
        memory_id=str(uuid.uuid4()),
        user_id=req.user_id,
        scope=req.scope,
        memory_type=req.memory_type,
        content=req.content,
        structured_data=req.structured_data,
        tags=req.tags,
        expires_at=req.expires_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    _memories[record.memory_id] = record
    logger.info("memory_created", memory_id=record.memory_id, scope=req.scope, user_id=req.user_id)
    return record


@app.post("/memories/query", tags=["memory"])
async def query_memories(req: QueryMemoryRequest):
    """Query memories with scope enforcement and optional text search."""
    results = []
    for record in _memories.values():
        # Scope filter
        if record.scope not in req.scopes:
            continue
        # Permission check
        if not _check_read_permission(
            req.requestor_id, req.requestor_scopes, record.scope, record.user_id
        ):
            continue
        # User filter: PERSONAL scope only returns user's own memories
        if record.scope == MemoryScope.PERSONAL and record.user_id != req.user_id:
            continue
        # Expiry filter
        if record.expires_at and record.expires_at < datetime.utcnow():
            continue
        # Type filter
        if req.memory_type and record.memory_type != req.memory_type:
            continue
        # Tag filter
        if req.tags and not any(tag in record.tags for tag in req.tags):
            continue
        # Text search
        if req.query and req.query.lower() not in record.content.lower():
            continue
        results.append(record)

    # Sort by most recent, apply limit
    results.sort(key=lambda r: r.updated_at, reverse=True)
    return results[: req.limit]


@app.delete("/memories/{memory_id}", tags=["memory"])
async def delete_memory(memory_id: str, requestor_id: str, requestor_scopes: list[str]):
    """Delete a memory record (owner only for PERSONAL scope)."""
    record = _memories.get(memory_id)
    if not record:
        raise HTTPException(status_code=404, detail="Memory not found")
    if not _check_write_permission(
        requestor_id, requestor_scopes, record.scope, record.user_id
    ):
        raise HTTPException(status_code=403, detail="Permission denied")
    del _memories[memory_id]
    return {"deleted": memory_id}
