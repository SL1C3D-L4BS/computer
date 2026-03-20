# Computer Runtime Kernel (CRK)

**Status:** Authoritative  
**Owner:** Platform  
**ADRs:** ADR-025 (CRK primary loop), ADR-029 (ExecutionContext first-class)  
**Contracts:** `packages/runtime-contracts/models.py`

---

## Principle

> Every request must have **one owner at every step**, one durable context, one authorization decision, one execution path, and one attention outcome.

This principle is immutable. Violations are architectural bugs.

---

## Entry-Point Invariant

**ALL requests from ALL surfaces go through `runtime-kernel POST /execute`.**

There is no second lifecycle path. Surfaces are dumb:

| Surface | What it does | What it does NOT do |
|---------|-------------|---------------------|
| `assistant-api` | Creates `InputEnvelope`, calls `/execute`, holds conversation history | Execute logic, invoke tools, create jobs, decide mode |
| `control-api` | Authenticates, normalizes, emits `InputEnvelope`, calls `/execute` | Context resolution, tool invocation, internal state |
| `voice-gateway` | Pipes to `assistant-api` → `runtime-kernel` | Bypass the chain |
| Any new surface | Creates `InputEnvelope`, calls `/execute` | Bypass the chain |

Two execution paths = different tracing, different auth, different memory behavior = bugs.

---

## The 10-Step CRK Execution Loop

```
1.  INPUT INGESTION       voice/chat/event → normalized InputEnvelope
2.  INTENT CLASSIFICATION intent_class, confidence, surface, user_id
3.  CONTEXT RESOLUTION    identity + memory_scope + mode + active_workflows  [context-router]
4.  PLAN GENERATION       AI proposal OR deterministic policy path            [model-router]
5.  WORKFLOW BINDING      durable (workflow-runtime) OR immediate             [runtime-kernel]
6.  AUTHORIZATION CHECK   authz-service: AuthzRequest w/ full AuthzContext   [authz-service]
7a. TOOL INVOCATION       mcp-gateway → MCP tools (personal/family/work/site-readonly)
7b. CONTROL JOB BINDING   orchestrator → canonical site-control jobs (HIGH-consequence)
8.  STATE UPDATE          jobs / memory / audit / digital-twin
9.  ATTENTION DECISION    attention-engine: INTERRUPT|QUEUE|DIGEST|SILENT    [attention-engine]
10. RESPONSE/RENDER       channel-appropriate output via ResponseEnvelope
```

### Step no-ops

For a simple informational request (e.g. "What time is it?"):
- Steps 5, 7b, 8 → `noop` (no workflow, no job, no state write)
- Step 7a → may invoke a time/info tool or resolve locally
- Steps 3, 6 → always run (context and auth are never skipped)
- Step 9 → always runs (attention decision is always made)

No step is skipped at the surface level. The kernel decides what no-ops.

### Step 7 — the core abstraction boundary

Step 7 is **split into two non-blurrable paths**. This is the most important design decision in the system.

**7a — Tool Invocation** (via `mcp-gateway`):
- Personal/family/work/site-readonly access
- Returns typed `structuredContent` via MCP protocol
- Governed by T0–T4 trust tier policy function
- Examples: weather query, calendar lookup, memory read, crop status read

**7b — Control Job Binding** (via `orchestrator`):
- HIGH-consequence site-control semantics
- Creates an orchestrator job with full state machine (PENDING → VALIDATING → APPROVED → EXECUTING → COMPLETED)
- Requires approval gates for HIGH/CRITICAL risk
- Produces an audit trail entry
- Examples: open irrigation valve, arm rover, enable greenhouse heater, unlock gate

**Never blur 7a and 7b.** A valve command is not just a tool call with high risk. It is a different execution semantic.

---

## ExecutionContext

The single object threaded through all 10 steps. Defined in `packages/runtime-contracts/models.py`.

```python
@dataclass
class ExecutionContext:
    request_id: str         # Unique per request
    user_id: str
    mode: Mode              # Resolved from {user_id × surface} sticky map
    surface: Surface
    intent_class: str       # e.g. "irrigation.query", "reminder.set", "heating.enable"
    memory_scope: MemoryScope
    active_workflow_ids: list[str]   # Temporal IDs currently in flight for this user
    risk_class: RiskClass
    origin: Origin
    trace_id: str           # OTEL trace ID — must persist across all steps
    # ... enriched at each step
```

**Immutability rule:** Never replace `ExecutionContext` mid-loop. Enrich it by creating a new instance with updated fields. The original is archived as an audit record at each step.

---

## Computer's State of Mind

Owned by `runtime-kernel GET /state`. Represents the system's current operational state.

```python
@dataclass
class ComputerState:
    mode_by_surface: dict[str, Mode]  # key: "user_id:surface"
    active_workflow_ids: list[str]    # All in-flight Temporal workflow IDs
    pending_commitments: list[str]    # Deferred tasks, reminders
    attention_load: float             # 0.0–1.0; affects interrupt threshold
    system_health_flags: list[str]    # e.g. ["MQTT_DOWN", "AI_DEGRADED"]
    active_emergency: bool
```

**attention_load** is consumed by the attention-engine interrupt scoring formula:
```
urgency × (1 - attention_load) × privacy_factor × time_weight
```

---

## Service API

### `POST /execute`

Accepts `InputEnvelope`. Runs the 10-step loop. Returns `ResponseEnvelope`.

Delegates to stub → real service chain:
- Step 3 → `context-router` (stub: echo mode from surface default)
- Step 4 → `model-router` (stub: `intent_class = "unknown"`, `plan_type = "deterministic_policy"`)
- Step 5 → `workflow-runtime` or inline (stub: IMMEDIATE binding)
- Step 6 → `authz-service` (stub: allow all with `reason = "stub_always_allow"`)
- Step 7a → `mcp-gateway` (stub: empty tools response)
- Step 7b → `orchestrator` (stub: return a mock job ID for HIGH-risk requests)
- Step 9 → `attention-engine` (stub: INTERRUPT for CRITICAL, QUEUE otherwise)

### `GET /state`

Returns `ComputerState`. Mode map starts empty; populated by first request per surface.

### `POST /interrupt`

Emergency bypass. Skips steps 1–4. Jumps to step 6 with:
- `risk_class = CRITICAL`
- `origin = OPERATOR`
- `intent_class = "emergency.interrupt"`

Used by: E-stop endpoint, security alarm escalation, operator emergency override.

---

## Failure Semantics

| Failure | Behavior |
|---------|----------|
| Step 3 (context) fails | Use surface-default mode; log degraded; continue |
| Step 4 (plan) fails | Use deterministic policy fallback; do not attempt AI path |
| Step 5 (workflow bind) fails | Downgrade to IMMEDIATE; log; continue |
| Step 6 (authz) fails or times out | **DENY and halt** — never allow on auth failure |
| Step 7a (tool) fails | Return error content; do not retry in-loop; log |
| Step 7b (control job) fails | Return error; do not silently drop; log with audit record |
| Step 9 (attention) fails | Default to QUEUE NORMAL; log |
| Any step panics/crashes | Return 500 with trace_id; write StepAuditRecord with status="error" |

**Auth failure is the only hard halt.** All other failures degrade gracefully with a logged noop.

---

## Audit Chain

At each step, runtime-kernel writes a `StepAuditRecord`:

```python
@dataclass
class StepAuditRecord:
    request_id: str
    trace_id: str
    step: str       # e.g. "6_authz_check", "7b_control_job_bind"
    status: str     # "ok" | "noop" | "stub" | "error"
    detail: str
    duration_ms: int
```

This forms the full audit chain for ADR-029 compliance and incident reconstruction.

---

## Related Documents

- `docs/architecture/kernel-authority-model.md` — who owns what
- `docs/architecture/workflow-orchestrator-boundary.md` — WR ↔ ORC contract
- `docs/product/mode-transition-rules.md` — mode stickiness and shared-device rules
- `packages/runtime-contracts/models.py` — all shared types
- `services/runtime-kernel/` — implementation
