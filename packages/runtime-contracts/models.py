"""
Computer Runtime Kernel — Shared Contract Types

Pure data definitions. No logic. No I/O. No side effects.
Imported by every service that participates in the CRK execution loop.

Canonical reference:    docs/architecture/runtime-kernel.md
Authority model:        docs/architecture/kernel-authority-model.md
State model:            docs/architecture/system-state-model.md
Uncertainty model:      docs/architecture/uncertainty-and-confidence-model.md
Objective functions:    docs/architecture/objective-functions.md
Formal invariants:      docs/safety/formal-invariants-and-proof-obligations.md

DO NOT add business logic here. This file is a schema, not a library.

SCALE CONVENTION (all float fields):
  Unless documented otherwise, all [0,1] fields use:
  - 1.0 = maximum/highest (most confident, most urgent, most fresh)
  - 0.0 = minimum/lowest (no confidence, no urgency, fully stale)
  - Monotonicity: higher value = better/more on the named dimension
  See docs/architecture/measurement-and-scaling-model.md for full rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enumerations ──────────────────────────────────────────────────────────────

class Mode(str, Enum):
    """
    Operating mode. Sticky per {user_id × surface}.
    Enforced at step 6 (AuthzRequest.context.mode).
    Never default to a higher-privilege mode.
    """
    PERSONAL   = "PERSONAL"
    FAMILY     = "FAMILY"
    WORK       = "WORK"
    SITE       = "SITE"
    EMERGENCY  = "EMERGENCY"


class Surface(str, Enum):
    """
    The physical or logical surface that originated the request.
    Determines mode stickiness per {user_id × surface}.
    """
    VOICE   = "VOICE"
    CHAT    = "CHAT"
    WEB     = "WEB"
    MOBILE  = "MOBILE"
    OPS     = "OPS"
    EVENT   = "EVENT"    # System-generated (schedules, sensor events, webhooks)


class MemoryScope(str, Enum):
    """
    Memory scope bound to the request. Enforces privacy boundaries.
    Requestors may only read memory within their own scope or lower.
    """
    PERSONAL          = "PERSONAL"
    HOUSEHOLD_SHARED  = "HOUSEHOLD_SHARED"
    WORK              = "WORK"
    SITE              = "SITE"
    GUEST_READ_ONLY   = "GUEST_READ_ONLY"


class RiskClass(str, Enum):
    """
    Risk classification of the request or tool.
    Drives approval mode in the orchestrator job state machine (ADR-007).
    risk_class and trust_tier are DIFFERENT AXES — never compare directly.
    """
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class Origin(str, Enum):
    """
    Who or what submitted the request.
    AI_ADVISORY may never auto-approve HIGH or CRITICAL jobs (ADR-002, F05).
    """
    OPERATOR     = "OPERATOR"
    AI_ADVISORY  = "AI_ADVISORY"
    SYSTEM       = "SYSTEM"
    SCHEDULE     = "SCHEDULE"


class Channel(str, Enum):
    """Output delivery channel for AttentionDecision."""
    VOICE   = "VOICE"
    WEB     = "WEB"
    MOBILE  = "MOBILE"
    OPS     = "OPS"


class AttentionAction(str, Enum):
    """
    How runtime-kernel delivers the response after step 9.
    SILENT = response is generated but not delivered to the user proactively.
    """
    INTERRUPT = "INTERRUPT"   # Speak/notify immediately
    QUEUE     = "QUEUE"       # Deliver at next natural pause
    DIGEST    = "DIGEST"      # Batch into next scheduled summary
    SILENT    = "SILENT"      # Log only; do not surface to user


class AttentionPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    NORMAL   = "NORMAL"
    LOW      = "LOW"


class WorkflowBindingType(str, Enum):
    """Whether the workflow is durable (Temporal) or immediate (inline)."""
    DURABLE   = "DURABLE"    # Temporal workflow — survives restarts
    IMMEDIATE = "IMMEDIATE"  # In-process, short-lived, no Temporal


# ── Core Types ────────────────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    """
    The single object threaded through all 10 steps of the CRK loop.
    Created at step 1, enriched at steps 2-3, carried through to step 10.
    Persisted in audit log at each step transition (ADR-029).

    IMMUTABLE RULE: never replace ExecutionContext mid-loop.
    Enrich it by returning a new instance with updated fields.
    """
    request_id:          str
    user_id:             str
    mode:                Mode
    surface:             Surface
    intent_class:        str            # e.g. "irrigation.query", "reminder.set"
    memory_scope:        MemoryScope
    active_workflow_ids: list[str]      # Temporal workflow IDs currently in flight
    risk_class:          RiskClass
    origin:              Origin
    trace_id:            str            # OTEL trace ID; must match across all steps

    # Enriched at step 3 (context-router)
    mode_change_reason:  str | None = None   # If mode changed from surface default, why
    session_id:          str | None = None

    # Enriched at step 4 (model-router)
    plan_type:           str | None = None   # "ai_proposal" | "deterministic_policy"

    # Enriched at step 5 (workflow binding)
    workflow_binding:    "WorkflowBinding | None" = None

    # System state snapshot at request time
    attention_load:      float = 0.0        # 0.0–1.0; affects interrupt threshold
    system_health_flags: list[str] = field(default_factory=list)  # e.g. ["MQTT_DOWN"]


@dataclass
class InputEnvelope:
    """
    Normalized input from any surface. Created by surfaces (assistant-api,
    control-api, voice-gateway). Never created by runtime-kernel itself.

    All surfaces MUST create an InputEnvelope and call POST /execute on
    runtime-kernel. There is no second lifecycle path.
    """
    raw_input:   str
    surface:     Surface
    user_id:     str
    session_id:  str
    trace_id:    str             # Caller generates; runtime-kernel carries through

    # Optional pre-classifications the surface can provide
    intent_hint:   str | None = None  # Surface-level intent hint (not authoritative)
    mode_hint:     Mode | None = None # Caller's suggestion; runtime-kernel may override
    metadata:      dict[str, Any] = field(default_factory=dict)


@dataclass
class AttentionDecision:
    """
    Output of step 9 (attention-engine).
    Part of execution, not a UI concern (ADR-028).

    decision:  how to deliver the response
    channel:   which channel to use
    audience:  which user_ids should receive it (may differ from request originator)
    reasoning: human-readable reason (for audit + debugging)
    delay_ms:  how long to wait before delivery (0 = immediate)
    priority:  delivery priority within the channel queue
    """
    decision:  AttentionAction
    channel:   Channel
    audience:  list[str]
    reasoning: str
    delay_ms:  int = 0
    priority:  AttentionPriority = AttentionPriority.NORMAL


@dataclass
class WorkflowBinding:
    """
    Output of step 5 (workflow binding decision).
    DURABLE = workflow_id is a Temporal workflow ID (survives restarts).
    IMMEDIATE = inline execution; workflow_id is a local request-scoped ID.
    """
    workflow_id:         str
    type:                WorkflowBindingType
    temporal_task_queue: str | None = None  # Required for DURABLE type
    job_id:              str | None = None  # Set when 7b (control job) is bound


@dataclass
class AuthzContext:
    """
    Full context passed to authz-service at step 6.
    mode is REQUIRED because the same user has different tool access by mode.
    risk_class and trust_tier are DIFFERENT AXES — authz-service uses a
    policy function, not a simple ordering comparison.
    """
    mode:         Mode
    risk_class:   RiskClass
    origin:       Origin
    location:     str | None = None       # Physical zone (e.g. "greenhouse", "office")
    time_of_day:  str | None = None       # ISO 8601 time string
    extra:        dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthzRequest:
    """
    Input to authz-service POST /authorize.
    subject: user or service making the request
    resource: what is being accessed (tool name, job type, memory scope, etc.)
    action: what operation is requested (read, write, invoke, create, approve)
    context: full AuthzContext (mode + risk_class + origin + location + time)
    """
    subject:  str
    resource: str
    action:   str
    context:  AuthzContext


@dataclass
class AuthzResponse:
    """Output of authz-service POST /authorize."""
    allowed:            bool
    reason:             str
    applicable_policy:  str   # Policy name or ID that determined the outcome


@dataclass
class ResponseEnvelope:
    """
    The final output of the CRK execution loop (step 10).
    Returned by runtime-kernel POST /execute.

    trace_id MUST match the InputEnvelope.trace_id.
    This is verified by the execution_loop operational rubric check.
    """
    content:            str
    channel:            Channel
    attention_decision: AttentionDecision
    proposed_jobs:      list[str]                      # Job IDs created at step 7b
    trace_id:           str                            # Must match InputEnvelope.trace_id
    workflow_binding:   WorkflowBinding | None = None  # Set if step 5 bound a workflow
    execution_context:  ExecutionContext | None = None # Optional: include for debugging
    metadata:           dict[str, Any] = field(default_factory=dict)


@dataclass
class ComputerState:
    """
    Computer's current state of mind. Returned by runtime-kernel GET /state.
    Per-surface mode map: key = "{user_id}:{surface}", value = Mode.

    V3: Extended with open loops, commitments, and follow-up queue.
    All loop/commitment fields carry typed priority_score, freshness, decay_at,
    and owner_confidence per docs/product/open-loop-mathematics.md.

    This is a READ-ONLY PROJECTION. It must never be written to directly.
    Update the canonical stores (workflow-runtime, memory-service) instead.
    """
    mode_by_surface:       dict[str, Mode]    # key: "user_id:surface"
    active_workflow_ids:   list[str]          # All in-flight Temporal workflow IDs
    attention_load:        float              # [0,1] current cognitive load estimate
    system_health_flags:   list[str]          # Degraded subsystem flags
    active_emergency:      bool = False

    # V3: Continuity state — open loops tracked by the mind loop
    open_loops:            list[OpenLoop]       = field(default_factory=list)

    # V3: Explicit commitments made to users
    pending_commitments:   list[Commitment]     = field(default_factory=list)

    # V3: Scheduled follow-up checks
    follow_up_queue:       list[FollowUp]       = field(default_factory=list)


# ── Step audit record ─────────────────────────────────────────────────────────

@dataclass
class StepAuditRecord:
    """
    Written at each CRK step transition. Forms the audit chain for ADR-029.
    Stored by runtime-kernel; queryable for debugging and compliance.
    """
    request_id:   str
    trace_id:     str
    step:         str       # e.g. "1_input_ingestion", "6_authz_check", "7b_control_job"
    status:       str       # "ok" | "noop" | "stub" | "error"
    detail:       str       # Human-readable description of what happened
    duration_ms:  int = 0
    metadata:     dict[str, Any] = field(default_factory=dict)


# ── V3 Scientific Types ────────────────────────────────────────────────────────
# Reference: docs/architecture/uncertainty-and-confidence-model.md
# Reference: docs/architecture/objective-functions.md
# Reference: docs/safety/formal-invariants-and-proof-obligations.md
#
# ALL instances of these types MUST be written to the audit log via
# runtime-kernel POST /audit. Unlogged instances are treated as non-existent
# for calibration and reflection purposes.


class ConfidenceType(str, Enum):
    """Type of confidence measurement. Each type has different decay and calibration rules."""
    IDENTITY     = "identity"      # Speaker/user certainty
    INTENT       = "intent"        # NLU/ASR match quality
    MODE         = "mode"          # Operating context correctness
    MEMORY       = "memory"        # Retrieved context reliability
    SEVERITY     = "severity"      # Event importance certainty
    TOOL_REC     = "tool_rec"      # Recommended action correctness
    ACTUATION    = "actuation"     # Safe-to-actuate certainty (composite)


class ObservationType(str, Enum):
    """User/system feedback event types for closed-loop learning."""
    ACKNOWLEDGMENT = "acknowledgment"  # User explicitly acknowledged
    DISMISSAL      = "dismissal"       # User explicitly dismissed
    SILENCE        = "silence"         # No response within timeout
    CORRECTION     = "correction"      # User corrected an error (supersedes inferred state)
    ESCALATION     = "escalation"      # User escalated urgency
    COMPLETION     = "completion"      # Task was fully resolved


class OpenLoopStatus(str, Enum):
    ACTIVE     = "ACTIVE"
    RESURFACED = "RESURFACED"   # Currently being surfaced to user
    CLOSED     = "CLOSED"       # User confirmed resolution
    ABANDONED  = "ABANDONED"    # Decayed past max_age; auto-closed
    CANCELLED  = "CANCELLED"    # Explicitly cancelled by user or operator


class ImplementationStatus(str, Enum):
    """Lifecycle status of scientific artifacts and their runtime implementations."""
    SPECIFIED       = "SPECIFIED"        # Contract written, not yet wired to code
    INSTRUMENTED    = "INSTRUMENTED"     # Code emits the typed objects
    CALIBRATED      = "CALIBRATED"       # Calibration tests pass
    VALIDATED       = "VALIDATED"        # Shadow eval confirms behavior matches spec
    PRODUCTION_GATED = "PRODUCTION_GATED"  # CI gate enforces on every commit


@dataclass
class ConfidenceScore:
    """
    Typed, decaying confidence measurement.
    Reference: docs/architecture/uncertainty-and-confidence-model.md

    Scale: [0.0, 1.0] — 1.0 = maximum certainty, 0.0 = no certainty.
    Normalization: min-max within type (see measurement-and-scaling-model.md).
    Decay: value should be recomputed at use time using:
        current_value = value * exp(-decay_rate_per_s * elapsed_s)
    """
    value:               float           # [0.0, 1.0] — confidence at computed_at
    type:                ConfidenceType
    source:              str             # Service/step that produced this score
    decay_rate_per_s:    float           # Per-second exponential decay rate (0 = no decay)
    computed_at:         str             # ISO 8601 timestamp

    def is_stale(self, max_age_s: float) -> bool:
        """Returns True if this score should no longer be trusted."""
        from datetime import datetime, timezone
        computed = datetime.fromisoformat(self.computed_at.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - computed).total_seconds()
        return age_s > max_age_s


@dataclass
class UncertaintyVector:
    """
    Per-type confidence snapshot for complex multi-step decisions.
    Used when multiple uncertainty sources interact (actuation proposals,
    multi-turn workflows, MEDIUM+ risk requests).
    Reference: docs/architecture/uncertainty-and-confidence-model.md
    """
    identity:   ConfidenceScore
    intent:     ConfidenceScore
    mode:       ConfidenceScore
    memory:     ConfidenceScore
    severity:   ConfidenceScore
    tool_rec:   ConfidenceScore
    actuation:  ConfidenceScore

    def effective_confidence_high_risk(self) -> float:
        """Hard minimum across all types. Use for HIGH/CRITICAL risk paths."""
        return min(
            self.identity.value, self.intent.value, self.mode.value,
            self.memory.value, self.severity.value, self.tool_rec.value,
            self.actuation.value
        )

    def effective_confidence_medium_risk(self) -> float:
        """Conservative weighted minimum. Use for MEDIUM risk paths."""
        values = [
            self.identity.value, self.intent.value, self.mode.value,
            self.memory.value, self.severity.value, self.tool_rec.value,
            self.actuation.value
        ]
        return 0.7 * min(values) + 0.3 * (sum(values) / len(values))


@dataclass
class InvariantCheckResult:
    """
    Result of an invariant check at runtime.
    MUST be written to audit log when passed=False.
    All violations increment the invariant_violation_count metric.
    Reference: docs/safety/formal-invariants-and-proof-obligations.md
    """
    invariant_id:         str             # e.g. "I-04", "I-06"
    passed:               bool
    evidence:             dict[str, Any]  # Key facts that determined the outcome
    checked_at:           str             # ISO 8601 timestamp
    enforcement_location: str             # Service + function where checked


@dataclass
class ObservationRecord:
    """
    User or system feedback captured after a decision was delivered.
    Powers the closed-loop learning path for attention and continuity.
    MUST be written to audit log for calibration.
    Reference: docs/architecture/transition-and-control-model.md (Agent 2)
    """
    trace_id:         str
    step:             str             # CRK step that emitted the decision being observed
    observation_type: ObservationType
    value:            Any             # The observed signal (ack text, dismissal reason, etc.)
    latency_ms:       int             # Time between decision delivery and observation
    confidence:       float           # [0,1] Confidence that observation is accurately captured
    user_id:          str | None = None
    context_snapshot: dict[str, Any] = field(default_factory=dict)  # Mode, surface, etc.


@dataclass
class AttentionCost:
    """
    Decomposed cost-benefit analysis for an attention delivery decision.
    All terms normalized to [0,1] per measurement-and-scaling-model.md.
    net_value is unbounded but clipped to [-1, 1] before comparison.
    Reference: docs/architecture/objective-functions.md (Domain 3)
    """
    interruption_cost:       float   # [0,1] cost of delivering right now
    urgency_value:           float   # [0,1] value of delivering now vs later
    privacy_risk:            float   # [0,1] risk of wrong audience receiving this
    predicted_ack_likelihood: float  # [0,1] estimated probability of user acknowledging
    time_to_decay_penalty:   float   # [0,1] value lost by delaying to next slot
    net_value:               float   # clipped to [-1, 1]; positive = worth delivering


@dataclass
class TrustSignal:
    """
    A discrete trust event from a user toward the assistant.
    Aggregated over time to compute trust_retention metric.
    Reference: docs/architecture/objective-functions.md (Domain 1)
    """
    user_id:     str
    signal_type: str     # "positive_correction" | "negative_correction" | "escalation"
                         # | "approval" | "explicit_praise" | "complaint"
    magnitude:   float   # [0,1] strength of the signal
    trace_id:    str     # The interaction that triggered this signal
    recorded_at: str     # ISO 8601


@dataclass
class StateEstimate:
    """
    A probabilistic estimate of a state variable with associated confidence.
    Used for human state estimates (attention load, availability, role).
    Reference: docs/architecture/system-state-model.md (Partition 3)
    """
    variable:     str            # Name of the state variable being estimated
    value:        Any            # The estimated value
    confidence:   ConfidenceScore
    valid_until:  str | None = None  # ISO 8601; None = no known expiry


@dataclass
class ControlAction:
    """
    A recorded control action taken by the CRK (step 7a or 7b).
    Used by reflection-engine to identify patterns in actuation decisions.
    Reference: docs/architecture/transition-and-control-model.md
    """
    action_id:     str
    action_type:   str           # "tool_invocation" | "control_job" | "workflow_start"
    step:          str           # "7a" or "7b"
    resource:      str           # Tool name, job type, or workflow name
    risk_class:    RiskClass
    outcome:       str           # "success" | "rejected" | "pending" | "failed"
    trace_id:      str
    executed_at:   str           # ISO 8601
    rationale:     "DecisionRationale | None" = None


@dataclass
class DisturbanceRecord:
    """
    A logged disturbance that affected a CRK execution.
    Powers transition analysis and reliability reporting.
    Reference: docs/architecture/transition-and-control-model.md (Disturbance Taxonomy)
    """
    disturbance_type: str        # From taxonomy: "asr_error" | "missing_identity" |
                                 # "stale_sensor" | "service_unavailable" | "stale_authz"
    severity:         str        # "low" | "medium" | "high" | "critical"
    affected_step:    str        # CRK step where disturbance occurred
    trace_id:         str
    occurred_at:      str        # ISO 8601
    recovery_action:  str | None = None  # What the system did to handle it
    metadata:         dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRationale:
    """
    Inspectable record of why a decision was made.
    Every significant CRK decision (step 6, 7a/7b, 9) must produce one.
    MUST be written to audit log.
    Reference: docs/architecture/objective-functions.md
    """
    decision:                str                  # The decision that was made
    inputs:                  dict[str, Any]       # Named inputs to the decision
    confidence:              ConfidenceScore      # Effective confidence at decision time
    objective_weights:       dict[str, float]     # Active objective terms and their weights
    constraints_checked:     list[str]            # Invariant IDs checked (e.g. ["I-04", "I-06"])
    hard_constraints_violated: list[str]          # Must be empty for action to proceed
    alternatives_considered: list[str]            # Other decisions that were evaluated
    decided_at:              str                  # ISO 8601


# ── V3 Open Loop Types ─────────────────────────────────────────────────────────

@dataclass
class OpenLoop:
    """
    A tracked open commitment that requires future follow-up.
    Decays over time; closed by resolution event or abandoned when too stale.
    Reference: docs/product/open-loop-mathematics.md
    """
    id:                        str
    description:               str
    user_id:                   str
    priority_score:            float           # [0,1] initial urgency × importance × recency
    freshness:                 float           # [0,1] decays from 1.0 toward 0.0 over time
    decay_function:            str             # "exponential" | "linear" | "step"
    decay_half_life_hours:     float           # Half-life for exponential; slope for linear
    closure_conditions:        list[str]       # Event types that close this loop
    owner_confidence:          ConfidenceScore # Certainty of who owns resolution
    resurfacing_schedule:      str             # cron expression or "event:<type>"
    max_age_hours:             float           # After this: ABANDONED if freshness < 0.05
    min_resurfacing_interval_s: float          # Never resurface more often than this
    status:                    OpenLoopStatus  = OpenLoopStatus.ACTIVE
    created_at:                str             = ""   # ISO 8601
    last_surfaced_at:          str | None      = None
    closed_at:                 str | None      = None
    trace_id_origin:           str             = ""   # Trace that created this loop


@dataclass
class Commitment:
    """
    A commitment made to a user that must be fulfilled.
    Stronger than an open loop — represents an explicit promise.
    Reference: docs/product/continuity-and-followup-model.md
    """
    id:              str
    description:     str
    user_id:         str
    due_at:          str | None      # ISO 8601 deadline, if known
    priority_score:  float           # [0,1]
    owner_confidence: ConfidenceScore
    workflow_id:     str | None = None  # Bound Temporal workflow, if any
    status:          str = "PENDING"   # PENDING | FULFILLED | FAILED | CANCELLED
    created_at:      str = ""
    trace_id_origin: str = ""


@dataclass
class FollowUp:
    """
    A scheduled follow-up check on a previous interaction.
    Lower-commitment than a Commitment; created when outcome is uncertain.
    """
    id:               str
    description:      str
    user_id:          str
    check_at:         str             # ISO 8601 scheduled time
    priority_score:   float           # [0,1]
    freshness:        float           # [0,1]
    context_trace_id: str             # Original interaction to follow up on
    status:           str = "PENDING" # PENDING | RESOLVED | DROPPED


# ── V4 Policy Tuning Types ─────────────────────────────────────────────────────
# Reference: docs/delivery/policy-publish-gate.md
#            docs/product/policy-tuning-console.md
#            ADR-036


@dataclass
class PolicyImpactReport:
    """
    Operator declaration of expected impact before a policy change is replayed.

    MUST be filed before replay begins (policy-publish-gate.md Rule 2).
    Immutable once filed. All fields required.

    Reference: docs/delivery/policy-publish-gate.md
    """
    parameter_changed:    str              # Which parameter is changing
    current_value:        Any              # Current value before change
    proposed_value:       Any              # Proposed new value
    affected_metrics:     list[str]        # KPI names expected to shift
    expected_direction:   dict[str, str]   # metric → "increase" | "decrease" | "neutral"
    confidence:           float            # 0–1: operator's prediction confidence
    filed_by:             str              # Operator identity (passkey subject)
    filed_at:             str              # ISO 8601 timestamp


@dataclass
class ExpectationDelta:
    """
    Records a human correction when the user overrides, stops, or redirects
    the system. Feeds into eval fixtures and CandidatePolicyAdjustment proposals.

    Captured via: computer expect
    Read by:      reflection engine when generating CandidatePolicyAdjustment

    Reference: docs/product/policy-tuning-console.md
    """
    trace_id:        str
    user_id:         str
    user_intent:     str              # What the user expected the system to do
    system_decision: str              # What the system actually did
    correction:      str              # What the user said/did instead
    correction_type: str              # "override" | "stop" | "not_now" | "correction" | "redirect"
    context:         dict[str, Any]
    captured_at:     str              # ISO 8601 timestamp
    id:              str = ""         # UUID assigned at capture
