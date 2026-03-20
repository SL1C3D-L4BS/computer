# Missing Runtime Planes

**Status:** Authoritative  
**Owner:** Platform  
**Contracts:** `packages/runtime-contracts/models.py`

This document specifies all 8 runtime planes introduced in Runtime Intelligence v2. Each plane is mapped to its CRK execution loop step, owning service/package, and acceptance tests using `runtime-contracts` types.

---

## Plane Overview

| Plane | CRK Step | Owning Service | Owning Package | Status |
|-------|----------|---------------|----------------|--------|
| Durable Workflows | 5 | `workflow-runtime` | — | v0.1 stub |
| Tool Fabric (MCP) | 7a | — | `mcp-gateway`, `mcp-tools`, `mcp-servers` | v0.1 stub |
| Authorization Graph | 6 | `authz-service` | `authz-model` | v0.1 stub |
| Attention | 9 | `attention-engine` | `runtime-contracts` | v0.1 stub |
| Local-First Sync | 10 | — | `sync-model` | planned |
| Voice Fluency | 1 | `voice-gateway` v2 | — | planned |
| AI Evaluation | cross | `eval-runner` | `eval-fixtures` | planned |
| Traceability | cross | otel-collector config | — | v0.1 config |

---

## Plane 1: Durable Workflows

**CRK Step:** 5 (Workflow Binding)  
**Service:** `services/workflow-runtime/`

### Objective
Provide fault-tolerant, long-lived workflow execution for any multi-step household or site task that must survive server restarts, network interruptions, or operator absence.

### Interface (uses runtime-contracts types)

```python
# Step 5 produces this; workflow-runtime executes it
WorkflowBinding(
    workflow_id="wf-household-routine-abc123",
    type=WorkflowBindingType.DURABLE,
    temporal_task_queue="computer-main",
    job_id=None  # Set when 7b is also bound
)

# workflow-runtime input (not an ExecutionContext; task-level params)
class StartWorkflowRequest:
    workflow_type: str       # "HouseholdRoutineWorkflow"
    workflow_id: str | None  # None = auto-generate
    args: dict
    task_queue: str = "computer-main"
```

### v1 Delivery
- Temporal Python SDK, `@workflow.defn`, `@activity.defn`
- SQLite dev server / Postgres prod server
- `HouseholdRoutineWorkflow` with signal (`job_approved`) + update (`get_status`)
- Activity retry policy: max 5 attempts, exponential backoff

### v2 Delivery
- Worker versioning for zero-downtime deploys
- Multi-workflow composition (e.g., irrigation + energy as sibling workflows)
- Workflow search attributes for `ExecutionContext.trace_id` queryability

### Acceptance Tests
```python
def test_workflow_binding_is_durable(response: ResponseEnvelope):
    assert response.workflow_binding.type == WorkflowBindingType.DURABLE
    assert response.workflow_binding.temporal_task_queue == "computer-main"
    assert response.workflow_binding.workflow_id is not None

def test_workflow_survives_restart():
    # Start workflow, kill server, restart, verify workflow resumes
    ...
```

### Failure Modes
- Temporal server down → CRK step 5 falls back to IMMEDIATE; log degraded
- Activity max retries exceeded → workflow fails with escalation signal to attention-engine
- Workflow drift (version mismatch) → use `@workflow.versioned` pattern

### Security
- Workflow IDs are scoped to `user_id` — no cross-user workflow access
- Signal/update endpoints require service auth (not exposed to end users)

---

## Plane 2: Tool Fabric (MCP)

**CRK Step:** 7a (Tool Invocation)  
**Package:** `packages/mcp-gateway/`, `packages/mcp-tools/`, `packages/mcp-servers/`

### Objective
Provide a uniform, policy-governed protocol for tool access. Replace ad-hoc function calls with a structured, typed, auditable tool invocation layer using MCP 2025-06-18.

### Interface

```python
# 7a input
class ToolInvokeRequest:
    tool_name: str
    arguments: dict
    execution_context: ExecutionContext  # Full context — mode, risk, origin, trace_id

# 7a output (MCP 2025 structuredContent)
class ToolInvokeResponse:
    tool_name: str
    structuredContent: dict | None  # Per tool's outputSchema
    content: str                    # Text rendering
    resource_links: list[dict]      # MCP 2025 resource_link type
    trace_id: str
    policy_applied: str
```

### Trust Tiers (T0-T4)
See `packages/mcp-gateway/mcp_gateway/policy.py` for full definitions.

- T0: Public info (no auth) — time, weather
- T1: Household info (FAMILY+ mode) — calendar, greenhouse status
- T2: Personal sensitive (PERSONAL/WORK/SITE) — memory, health
- T3: Site read-only (SITE/WORK) — job list, sensor data
- T4: Site operational (SITE/WORK + non-AI origin) — site config

T5 (direct actuation) is never registered.

### v1 Delivery
- Policy function in `mcp_gateway/policy.py`
- Registry in `mcp_gateway/registry.py`
- OAuth 2.1 auth skeleton (RFC 9728 / RFC 8414 / RFC 8707)
- Stub tool execution; replace with real MCP server calls

### v2 Delivery
- Real MCP server connections (`packages/mcp-servers/`)
- Elicitation: when MCP server requests user input, route through attention-engine step 9
- `resource_link` content type for structured references

### Acceptance Tests
```python
def test_drone_arm_never_registered():
    assert get_tool("drone.arm") is None

def test_t2_blocked_in_family_mode():
    result = evaluate(PolicyRequest(tool=memory_tool, mode="FAMILY", ...))
    assert not result.allowed

def test_ai_advisory_cannot_invoke_t3():
    result = evaluate(PolicyRequest(tool=site_jobs, origin="AI_ADVISORY", ...))
    assert not result.allowed
```

### Failure Modes
- MCP server unreachable → return stub response; log; do not halt request
- Auth discovery fails (RFC 9728) → return 401 with WWW-Authenticate header
- Policy deny → 403 with `{rule, reason, trace_id}`

### Security
- All invocations logged with trace_id and policy_applied
- Drone arm is never a registered tool (ADR-002, ADR-005)
- Control job actuation is never through this gateway (step 7b only)

---

## Plane 3: Authorization Graph

**CRK Step:** 6 (Authorization Check)  
**Service:** `services/authz-service/`  
**Package (v2):** `packages/authz-model/`

### Objective
Provide contextual authorization decisions for every CRK request. v1: RBAC. v2: ReBAC (relationship-based access control for household member hierarchies).

### Interface

```python
# Step 6 input (from runtime-contracts)
AuthzRequest(
    subject="founder_001",
    resource="site_control.irrigation.enable",
    action="execute",
    context=AuthzContext(
        mode=Mode.SITE,
        risk_class=RiskClass.HIGH,
        origin=Origin.OPERATOR,
        location="greenhouse",
        time_of_day="14:30",
    )
)

# Step 6 output
AuthzResponse(
    allowed=True,
    reason="v1 RBAC: OPERATOR in SITE mode allowed HIGH-risk site_control",
    applicable_policy="v1_rbac_default_allow",
)
```

### v1 Delivery
- RBAC policy function in `authz_service/main.py`
- Rules: emergency restriction, AI_ADVISORY guard, FAMILY isolation, PERSONAL site guard
- Mode is required in every request

### v2 Delivery
- ReBAC: household member graph (owner > adult > teen > child > guest)
- Relationship-aware: "Alice shares greenhouse access with Bob" as a resource relationship
- Token audience binding (RFC 8707) enforcement in this service

### Acceptance Tests
```python
def test_ai_advisory_cannot_approve_high_risk(client):
    r = client.post("/authorize", json={
        "subject": "ai_001", "resource": "job_approval", "action": "approve",
        "context": {"mode": "SITE", "risk_class": "HIGH", "origin": "AI_ADVISORY"}
    })
    assert not r.json()["allowed"]

def test_family_mode_cannot_access_personal(client):
    r = client.post("/authorize", json={
        "subject": "user", "resource": "personal.notes", "action": "read",
        "context": {"mode": "FAMILY", "risk_class": "LOW", "origin": "OPERATOR"}
    })
    assert not r.json()["allowed"]
```

### Failure Modes
- Service unreachable → runtime-kernel DENIES (hard rule — never allow on timeout)
- Policy error → return 500; runtime-kernel treats as deny

### Security
- Never authenticates — only authorizes (authentication is identity-service)
- Must be deployed with authz, never bypassed, even in degraded mode

---

## Plane 4: Attention

**CRK Step:** 9 (Attention Decision)  
**Service:** `services/attention-engine/`  
**Types:** `packages/runtime-contracts/models.py` — `AttentionDecision`

### Objective
Decide how and when to deliver the response to the user. This is an execution decision, not a UI decision. The attention plane prevents notification fatigue and respects user context.

### Interface

```python
# Step 9 input
class AttentionEvaluateRequest:
    urgency: float         # 0.0–1.0
    attention_load: float  # From ComputerState.attention_load
    privacy_factor: float  # 1.0 = shareable, 0.0 = private only
    time_weight: float     # 1.0 = immediate, 0.0 = can wait

# Step 9 output (from runtime-contracts)
AttentionDecision(
    decision=AttentionAction.INTERRUPT,
    channel=Channel.VOICE,
    audience=["founder_001"],
    reasoning="score=0.85 ≥ 0.7 threshold",
    delay_ms=0,
    priority=AttentionPriority.HIGH,
)
```

### Scoring Formula
```
score = urgency × (1 - attention_load) × privacy_factor × time_weight
CRITICAL risk → always INTERRUPT (override formula)
score ≥ 0.7 → INTERRUPT
score ≥ 0.4 → QUEUE
score ≥ 0.2 → DIGEST
score < 0.2 → SILENT
```

### v1 Delivery
- Formula-based scoring in `attention_engine/main.py`
- Mode-aware channel resolution
- CRITICAL risk override

### v2 Delivery
- Personalization: per-user interrupt sensitivity profiles
- Presence-aware: suppress INTERRUPT if user is in a meeting
- Batch DIGEST delivery on schedule

### Failure Modes
- Service unreachable → fallback to QUEUE NORMAL
- Invalid response → fallback to QUEUE NORMAL; never halt the loop

---

## Plane 5: Local-First Sync

**CRK Step:** 10 (Response/Render — family-web resilience)  
**Package:** `packages/sync-model/`

### Objective
Allow `family-web` to function offline and sync state when reconnected. Prevents data loss when the homestead network is intermittently unavailable.

### Interface

```python
# sync-model types (planned)
class SyncConflict:
    local_value: Any
    remote_value: Any
    field_path: str
    resolution: str  # "local_wins" | "remote_wins" | "merge" | "user_prompt"

class CRDTOperation:
    type: str  # "set" | "delete" | "increment" | "append"
    field_path: str
    value: Any
    vector_clock: dict[str, int]
    actor_id: str
```

### v1 Delivery
- `packages/sync-model/` types definition
- family-web offline mode with localStorage queue
- Sync on reconnect via context-router

### Failure Modes
- Permanent conflict → surface to user for manual resolution
- Clock skew → prefer latest timestamp with merge

---

## Plane 6: Voice Fluency

**CRK Step:** 1 (Input Ingestion) — enhanced voice preprocessing  
**Service:** `voice-gateway` v2

### Objective
Improve voice interaction quality: barge-in, turn detection, low-confidence fallback, speaker-aware routing, privacy suppression, shared-device handling.

### Interface

```python
# voice-gateway adds to InputEnvelope
class VoiceInputMetadata:
    speaker_confidence: float       # 0.0–1.0 voice print match
    ambient_noise_db: float
    is_barge_in: bool               # Interrupted a previous response
    turn_detection_confidence: float
    room_id: str                    # e.g. "kitchen", "office"
    identified_speaker_id: str | None  # None if uncertain
```

### Shared-Device Ambiguity Rule
If `speaker_confidence < 0.7` or `identified_speaker_id is None`:
- `InputEnvelope.mode_hint = Mode.FAMILY` (downgrade to low-trust)
- Suppress PERSONAL, WORK, SITE memory access
- Require identity confirmation before granting scoped access
- See: `docs/product/mode-transition-rules.md`

---

## Plane 7: AI Evaluation

**CRK Step:** Cross-cutting  
**Service:** `services/eval-runner/`  
**Package:** `packages/eval-fixtures/`

### Objective
Behavioral regression testing for AI components. Prevent AI quality regressions from shipping to production.

### Eval Categories

| Category | Description | ADR |
|----------|-------------|-----|
| `wrong_memory_scope` | AI reads personal memory in FAMILY mode | ADR-002 |
| `wrong_mode_routing` | Wrong mode assigned to surface | ADR-032 |
| `wrong_tool_tier` | T2+ tool invoked by AI_ADVISORY | ADR-018 |
| `unsafe_suggestion` | AI suggests high-risk action without operator | ADR-002 |
| `privacy_leakage` | Personal data in non-personal response | ADR-002 |
| `excessive_interrupt` | INTERRUPT when QUEUE was appropriate | ADR-028 |
| `no_actuation_violation` | Assistant creates job directly (not proposed) | ADR-002, F01 |

### Interface

```python
class EvalFixture:
    id: str
    category: str
    input_envelope: InputEnvelope
    expected_response: dict      # Partial match
    must_not_contain: list[str]  # Strings that must NOT appear
    expected_7b_noop: bool       # If True, no jobs must be created
    trace_id: str

class EvalResult:
    fixture_id: str
    passed: bool
    failures: list[str]
    actual_response: ResponseEnvelope
```

---

## Plane 8: Traceability

**CRK Step:** Cross-cutting  
**Config:** `infra/otel/otel-collector.yml`

### Objective
End-to-end observability: one trace = voice input to response. Every CRK step is a span. `trace_id` threads through `ExecutionContext`.

### Span Naming
```
crk.1_input_ingestion
crk.2_intent_classification
crk.3_context_resolution
crk.4_plan_generation
crk.5_workflow_binding
crk.6_authz_check
crk.7a_tool_invocation
crk.7b_control_job_bind
crk.8_state_update
crk.9_attention_decision
crk.10_response_render
```

### Stack
- **Collector:** OpenTelemetry Collector (`infra/otel/otel-collector.yml`)
- **Tracing backend:** Tempo
- **Log aggregation:** Loki
- **Metrics:** Prometheus + spanmetrics connector
- **Visualization:** Grafana

### Connectors
- `spanmetrics`: auto-generate latency + error rate metrics from spans
- `servicegraph`: dependency map from span relationships
- `routing`: route HIGH-risk spans to dedicated pipeline
