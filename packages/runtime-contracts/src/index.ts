/**
 * Computer Runtime Kernel — Shared Contract Types (TypeScript)
 *
 * Mirror of packages/runtime-contracts/models.py
 * Consumed by: ops-web, family-web, mcp-gateway (if migrated to TS)
 *
 * Pure type definitions. No logic. No I/O.
 *
 * V3 Scientific Types added per:
 *   docs/architecture/uncertainty-and-confidence-model.md
 *   docs/architecture/objective-functions.md
 *   docs/safety/formal-invariants-and-proof-obligations.md
 */

// ── Enumerations ─────────────────────────────────────────────────────────────

export type Mode =
  | "PERSONAL"
  | "FAMILY"
  | "WORK"
  | "SITE"
  | "EMERGENCY";

export type Surface =
  | "VOICE"
  | "CHAT"
  | "WEB"
  | "MOBILE"
  | "OPS"
  | "EVENT";

export type MemoryScope =
  | "PERSONAL"
  | "HOUSEHOLD_SHARED"
  | "WORK"
  | "SITE"
  | "GUEST_READ_ONLY";

export type RiskClass =
  | "LOW"
  | "MEDIUM"
  | "HIGH"
  | "CRITICAL";

export type Origin =
  | "OPERATOR"
  | "AI_ADVISORY"
  | "SYSTEM"
  | "SCHEDULE";

export type Channel =
  | "VOICE"
  | "WEB"
  | "MOBILE"
  | "OPS";

export type AttentionAction =
  | "INTERRUPT"
  | "QUEUE"
  | "DIGEST"
  | "SILENT";

export type AttentionPriority =
  | "CRITICAL"
  | "HIGH"
  | "NORMAL"
  | "LOW";

export type WorkflowBindingType =
  | "DURABLE"
  | "IMMEDIATE";

// ── Core Types ────────────────────────────────────────────────────────────────

/**
 * Threaded through all 10 steps of the CRK loop.
 * See: docs/architecture/runtime-kernel.md
 */
export interface ExecutionContext {
  request_id: string;
  user_id: string;
  mode: Mode;
  surface: Surface;
  intent_class: string;
  memory_scope: MemoryScope;
  active_workflow_ids: string[];
  risk_class: RiskClass;
  origin: Origin;
  trace_id: string;

  // Optional enrichments
  mode_change_reason?: string;
  session_id?: string;
  plan_type?: "ai_proposal" | "deterministic_policy";
  workflow_binding?: WorkflowBinding;
  attention_load?: number;        // 0.0–1.0
  system_health_flags?: string[];
}

/**
 * Normalized input from any surface.
 * ALL surfaces must create this and call POST /execute on runtime-kernel.
 * No surface bypasses the CRK lifecycle.
 */
export interface InputEnvelope {
  raw_input: string;
  surface: Surface;
  user_id: string;
  session_id: string;
  trace_id: string;
  intent_hint?: string;
  mode_hint?: Mode;
  metadata?: Record<string, unknown>;
}

export interface AttentionDecision {
  decision: AttentionAction;
  channel: Channel;
  audience: string[];
  reasoning: string;
  delay_ms?: number;
  priority?: AttentionPriority;
}

export interface WorkflowBinding {
  workflow_id: string;
  type: WorkflowBindingType;
  temporal_task_queue?: string;
  job_id?: string;
}

export interface AuthzContext {
  mode: Mode;
  risk_class: RiskClass;
  origin: Origin;
  location?: string;
  time_of_day?: string;
  extra?: Record<string, unknown>;
}

export interface AuthzRequest {
  subject: string;
  resource: string;
  action: string;
  context: AuthzContext;
}

export interface AuthzResponse {
  allowed: boolean;
  reason: string;
  applicable_policy: string;
}

/**
 * Final output of the CRK loop.
 * trace_id MUST match the InputEnvelope.trace_id — verified by operational rubric.
 */
export interface ResponseEnvelope {
  content: string;
  channel: Channel;
  attention_decision: AttentionDecision;
  proposed_jobs: string[];
  trace_id: string;
  workflow_binding?: WorkflowBinding;
  execution_context?: ExecutionContext;
  metadata?: Record<string, unknown>;
}

/**
 * Computer's state of mind. Returned by GET /state on runtime-kernel.
 */
export interface ComputerState {
  mode_by_surface: Record<string, Mode>;  // key: "user_id:surface"
  active_workflow_ids: string[];
  pending_commitments: string[];
  attention_load: number;
  system_health_flags: string[];
  active_emergency: boolean;
}

export interface StepAuditRecord {
  request_id: string;
  trace_id: string;
  step: string;
  status: "ok" | "noop" | "stub" | "error";
  detail: string;
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

// ── V3 Scientific Types ───────────────────────────────────────────────────────

export type ConfidenceType =
  | "identity"
  | "intent"
  | "mode"
  | "memory"
  | "severity"
  | "tool_rec"
  | "actuation";

export type ObservationType =
  | "acknowledgment"
  | "dismissal"
  | "silence"
  | "correction"
  | "escalation"
  | "completion";

export type OpenLoopStatus =
  | "ACTIVE"
  | "RESURFACED"
  | "CLOSED"
  | "ABANDONED"
  | "CANCELLED";

export type ImplementationStatus =
  | "SPECIFIED"
  | "INSTRUMENTED"
  | "CALIBRATED"
  | "VALIDATED"
  | "PRODUCTION_GATED";

/** Typed, decaying confidence score. Scale [0,1]. */
export interface ConfidenceScore {
  value: number;             // [0.0, 1.0]
  type: ConfidenceType;
  source: string;            // Service/step that produced this
  decay_rate_per_s: number;  // 0 = no decay
  computed_at: string;       // ISO 8601
}

/** Per-type confidence snapshot for complex multi-step decisions. */
export interface UncertaintyVector {
  identity: ConfidenceScore;
  intent: ConfidenceScore;
  mode: ConfidenceScore;
  memory: ConfidenceScore;
  severity: ConfidenceScore;
  tool_rec: ConfidenceScore;
  actuation: ConfidenceScore;
}

/** Result of an invariant check. Must be logged when passed=false. */
export interface InvariantCheckResult {
  invariant_id: string;       // e.g. "I-04"
  passed: boolean;
  evidence: Record<string, unknown>;
  checked_at: string;         // ISO 8601
  enforcement_location: string;
}

/** User/system feedback captured after a decision was delivered. */
export interface ObservationRecord {
  trace_id: string;
  step: string;
  observation_type: ObservationType;
  value: unknown;
  latency_ms: number;
  confidence: number;         // [0,1]
  user_id?: string;
  context_snapshot?: Record<string, unknown>;
}

/** Decomposed attention delivery cost-benefit. All terms [0,1] except net_value [-1,1]. */
export interface AttentionCost {
  interruption_cost: number;
  urgency_value: number;
  privacy_risk: number;
  predicted_ack_likelihood: number;
  time_to_decay_penalty: number;
  net_value: number;          // clipped to [-1, 1]
}

/** A discrete trust signal from a user. */
export interface TrustSignal {
  user_id: string;
  signal_type: "positive_correction" | "negative_correction" | "escalation"
             | "approval" | "explicit_praise" | "complaint";
  magnitude: number;  // [0,1]
  trace_id: string;
  recorded_at: string;
}

/** Probabilistic estimate of a state variable. */
export interface StateEstimate {
  variable: string;
  value: unknown;
  confidence: ConfidenceScore;
  valid_until?: string;
}

/** A recorded control action taken by the CRK. */
export interface ControlAction {
  action_id: string;
  action_type: "tool_invocation" | "control_job" | "workflow_start";
  step: "7a" | "7b";
  resource: string;
  risk_class: RiskClass;
  outcome: "success" | "rejected" | "pending" | "failed";
  trace_id: string;
  executed_at: string;
  rationale?: DecisionRationale;
}

/** Logged disturbance affecting a CRK execution. */
export interface DisturbanceRecord {
  disturbance_type: string;
  severity: "low" | "medium" | "high" | "critical";
  affected_step: string;
  trace_id: string;
  occurred_at: string;
  recovery_action?: string;
  metadata?: Record<string, unknown>;
}

/** Inspectable record of why a decision was made. Must be logged. */
export interface DecisionRationale {
  decision: string;
  inputs: Record<string, unknown>;
  confidence: ConfidenceScore;
  objective_weights: Record<string, number>;
  constraints_checked: string[];
  hard_constraints_violated: string[];
  alternatives_considered: string[];
  decided_at: string;
}

// ── V3 Open Loop Types ────────────────────────────────────────────────────────

/** A tracked open commitment that decays over time. */
export interface OpenLoop {
  id: string;
  description: string;
  user_id: string;
  priority_score: number;           // [0,1]
  freshness: number;                // [0,1] decays toward 0
  decay_function: "exponential" | "linear" | "step";
  decay_half_life_hours: number;
  closure_conditions: string[];
  owner_confidence: ConfidenceScore;
  resurfacing_schedule: string;
  max_age_hours: number;
  min_resurfacing_interval_s: number;
  status: OpenLoopStatus;
  created_at: string;
  last_surfaced_at?: string;
  closed_at?: string;
  trace_id_origin: string;
}

/** An explicit commitment made to a user. */
export interface Commitment {
  id: string;
  description: string;
  user_id: string;
  due_at?: string;
  priority_score: number;    // [0,1]
  owner_confidence: ConfidenceScore;
  workflow_id?: string;
  status: "PENDING" | "FULFILLED" | "FAILED" | "CANCELLED";
  created_at: string;
  trace_id_origin: string;
}

/** A scheduled follow-up check. */
export interface FollowUp {
  id: string;
  description: string;
  user_id: string;
  check_at: string;
  priority_score: number;    // [0,1]
  freshness: number;         // [0,1]
  context_trace_id: string;
  status: "PENDING" | "RESOLVED" | "DROPPED";
}

/** V3 extended ComputerState with open loops and continuity. */
export interface ComputerState {
  mode_by_surface: Record<string, Mode>;
  active_workflow_ids: string[];
  attention_load: number;
  system_health_flags: string[];
  active_emergency: boolean;

  // V3 continuity
  open_loops: OpenLoop[];
  pending_commitments: Commitment[];
  follow_up_queue: FollowUp[];
}
