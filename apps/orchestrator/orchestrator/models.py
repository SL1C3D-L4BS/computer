"""
Orchestrator domain models — job, state machine, command log, audit events.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobState(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class JobOrigin(str, Enum):
    OPERATOR = "OPERATOR"
    POLICY = "POLICY"
    AI_ADVISORY = "AI_ADVISORY"
    SENSOR_RULE = "SENSOR_RULE"
    EMERGENCY = "EMERGENCY"


class RiskClass(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalMode(str, Enum):
    NONE = "NONE"
    AUTO = "AUTO"
    AUTO_WITH_AUDIT = "AUTO_WITH_AUDIT"
    OPERATOR_REQUIRED = "OPERATOR_REQUIRED"
    OPERATOR_CONFIRM_TWICE = "OPERATOR_CONFIRM_TWICE"


class CommandLogEntryType(str, Enum):
    DISPATCH = "DISPATCH"
    ACK = "ACK"
    NACK = "NACK"
    RETRY = "RETRY"
    TIMEOUT = "TIMEOUT"
    ABORT = "ABORT"
    COMPLETE = "COMPLETE"


class Precondition(BaseModel):
    type: str
    description: str
    satisfied: bool | None = None
    checked_at: datetime | None = None


class AbortCondition(BaseModel):
    type: str
    description: str
    triggered: bool = False


class CommandLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: CommandLogEntryType
    dispatched_by: str
    target_service: str | None = None
    command_topic: str | None = None
    payload_summary: str | None = None
    outcome: str | None = None


class ApprovalEvent(BaseModel):
    approved_by: str
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    approval_note: str | None = None


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str | None = None
    type: str
    requested_by: str
    origin: JobOrigin
    target_asset_ids: list[str]
    target_capability: str | None = None
    target_zone: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk_class: RiskClass
    approval_mode: ApprovalMode
    state: JobState = JobState.PENDING
    preconditions: list[Precondition] = Field(default_factory=list)
    abort_conditions: list[AbortCondition] = Field(default_factory=list)
    command_log: list[CommandLogEntry] = Field(default_factory=list)
    telemetry_refs: list[str] = Field(default_factory=list)
    approval_event: ApprovalEvent | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    timeout_seconds: int = 300


class JobSubmitRequest(BaseModel):
    type: str
    requested_by: str
    origin: JobOrigin
    target_asset_ids: list[str]
    target_capability: str | None = None
    target_zone: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk_class: RiskClass
    request_id: str | None = None
    timeout_seconds: int = 300


class JobApprovalRequest(BaseModel):
    approved_by: str
    approval_note: str | None = None
    second_confirmation: bool = False  # Required for OPERATOR_CONFIRM_TWICE


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "down"
    service: str = "orchestrator"
    version: str = "0.1.0"
    dependencies: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=datetime.utcnow)
