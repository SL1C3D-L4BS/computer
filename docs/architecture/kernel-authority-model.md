# Kernel Authority Model

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-030  
**Enforcement rule:** Any PR that moves authority from one cell to another REQUIRES an ADR update.

---

## Purpose

Eliminates dual-kernel drift. Defines exactly what each component owns and does not own. Without this table, `runtime-kernel` and `orchestrator` will accumulate overlapping authority through implementation entropy.

---

## Authority Table

| Component | Owns | Does NOT own |
|-----------|------|--------------|
| `runtime-kernel` | Request lifecycle (all 10 steps), context assembly, plan routing, workflow binding (step 5), auth callout (step 6), attention callout (step 9), response assembly, step audit chain | Job state transitions, site-control command dispatch, conversation history, session persistence |
| `orchestrator` | Canonical job state machine (PENDING→VALIDATING→APPROVED→EXECUTING→COMPLETED/FAILED/ABORTED), site-control execution semantics, command dispatch to MQTT, job audit trail, approval management | Request lifecycle, context resolution, attention routing, personal/family tool access |
| `assistant-api` | Conversation/session API, chat history, voice session state, `InputEnvelope` creation | Execution logic, tool invocation, job creation, mode resolution, ExecutionContext management |
| `control-api` | External request surface (approval, query, submit), API authentication, rate limiting, `InputEnvelope` emission | Execution orchestration, context resolution, tool invocation, internal state |
| `workflow-runtime` | Durable task execution (Temporal), long-lived workflow state, timer management, signal/update handling | Direct hardware actuation (MQTT publish), job state ownership, orchestrator job transitions |
| `mcp-gateway` | Tool access mediation, policy function evaluation, MCP auth flow (OAuth 2.1), structured output normalization | Control job semantics, orchestrator interaction, drone arm registration |
| `authz-service` | Authorization decisions with full `AuthzContext`, policy function evaluation | Authentication (that is identity-service), session management |
| `attention-engine` | Interrupt/digest/silent delivery decisions with audience routing | UI rendering, notification infrastructure, mode decisions |
| `context-router` | Identity resolution, memory scope assignment, mode confirmation from sticky map | Mode enforcement (that is authz-service at step 6), tool routing |
| `model-router` | AI plan generation, tool selection proposal, propose-job endpoint | Job approval, job execution, direct tool invocation |
| `memory-service` | Scoped memory read/write, privacy boundary enforcement between scopes | Mode decisions, authorization decisions |
| `identity-service` | Device identity, user authentication tokens, household member registry | Authorization (that is authz-service), session state |

---

## Non-Overlapping Kernel Split

The two most dangerous overlap candidates:

### `runtime-kernel` vs `orchestrator`

```
runtime-kernel = request lifecycle kernel
orchestrator   = job/command execution engine
```

- `runtime-kernel` receives a request, runs 10 steps, binds a job at step 7b, returns a response.
- `orchestrator` receives that job, manages its state machine, dispatches commands.
- They communicate via `control-api` job submission or direct internal job API.
- `runtime-kernel` does NOT transition job states. `orchestrator` does NOT run the CRK loop.

### `assistant-api` vs `runtime-kernel`

```
assistant-api  = conversation surface (dumb)
runtime-kernel = execution lifecycle (smart)
```

- `assistant-api` holds chat history and session state only.
- Every request, including simple chat, becomes an `InputEnvelope` and goes to `/execute`.
- `assistant-api` does NOT decide which steps to skip. `runtime-kernel` decides.

---

## Drift Prevention Checklist

Before merging any PR that touches service boundaries, verify:

- [ ] No service directly publishes to MQTT except `orchestrator`
- [ ] No service calls `runtime-kernel /execute` except surfaces (assistant-api, control-api)
- [ ] No service approves orchestrator jobs except operator-authenticated paths
- [ ] No service reads another service's database directly (only via API)
- [ ] `mcp-gateway` never registers drone arm as a tool
- [ ] `workflow-runtime` never directly actuates hardware
- [ ] `authz-service` never authenticates (only authorizes)
- [ ] `assistant-api` never creates orchestrator jobs directly

If any check fails, do not merge. Open an ADR to formalize the authority change first.

---

## Adding New Components

When adding a new service or package, it must declare in its README:

```markdown
## Authority
**Owns:** [explicit list]
**Does NOT own:** [explicit list]
**Reports to CRK step:** [step number, or "none" for infrastructure]
```

This requirement is enforced by the structural rubric.

---

## Related Documents

- `docs/architecture/runtime-kernel.md`
- `docs/architecture/workflow-orchestrator-boundary.md`
- `docs/adr/ADR-030-kernel-authority-model.md`
