# CLI Command Reference

> Complete reference for all `computer` CLI commands, Taskfile tasks, and utility scripts.

---

## computer CLI

Entry point: `python3 scripts/cli/computer.py`

Version: `computer --version` → `4.0.0`

---

### Core 8 — Essential Operator Surface

#### `computer doctor [--fix]`

Runs full system health check: service liveness, version drift vs `versions.json`, MCP registry integrity, trace pipeline sanity, policy checksum.

```bash
python3 scripts/cli/computer.py doctor
python3 scripts/cli/computer.py doctor --fix   # apply safe auto-remediations
```

Checks performed:

| Check | Pass condition |
|-------|---------------|
| Service health | All core services return `200 /health` |
| Version drift | `node`, `python`, `pnpm` match `versions.json` |
| MCP registry | ≥32 tools registered |
| Trace pipeline | `audit_log.jsonl` is writable and recent |
| Policy checksum | Current checksum matches last checkpoint |

---

#### `computer trace <trace_id>`

Prints the full CRK execution chain for a trace: all 10 steps, confidence values, auth decisions, 7a/7b split, attention outcome.

```bash
python3 scripts/cli/computer.py trace tr-abc123
```

Output includes: `ExecutionContext` summary, per-step timing, `DecisionRationale`, `AttentionDecision`.

---

#### `computer explain <trace_id>`

Human-readable narration of why Computer chose INTERRUPT vs DIGEST vs SUPPRESS for a given trace.

```bash
python3 scripts/cli/computer.py explain tr-abc123
```

Output: decision in plain English, top 3 contributing factors, confidence, whether decision was later validated.

---

#### `computer replay <trace_id>`

Re-runs a historical `ExecutionContext` through the current policy stack and outputs a diff vs the original decision.

```bash
python3 scripts/cli/computer.py replay tr-abc123
```

---

#### `computer simulate <scenario>`

Runs an assistant scenario from `tests/scenarios/assistant/` and prints structured PASS/FAIL output.

```bash
python3 scripts/cli/computer.py simulate family_dinner
python3 scripts/cli/computer.py simulate --list    # list available scenarios
```

---

#### `computer workflow <subcommand>`

Manage durable Temporal workflows.

```bash
python3 scripts/cli/computer.py workflow list
python3 scripts/cli/computer.py workflow inspect <workflow_id>
python3 scripts/cli/computer.py workflow resume <workflow_id>
python3 scripts/cli/computer.py workflow cancel <workflow_id>
python3 scripts/cli/computer.py workflow sweep        # detect stale/orphaned
```

---

#### `computer auth check <subject> <action> <resource>`

Dry-run authorization check. Prints the ALLOW/DENY decision, reason, and policy path.

```bash
python3 scripts/cli/computer.py auth check user:founder approve memory_export
python3 scripts/cli/computer.py auth check user:family_member read shopping_list
```

---

#### `computer memory audit [--gc]`

Shows memory by scope, freshness distribution, hazard states, archived items, and cross-scope leakage checks.

```bash
python3 scripts/cli/computer.py memory audit
python3 scripts/cli/computer.py memory audit --gc    # dry-run GC recommendations
```

---

### Extended 13 — Trust, Policy, and Human Alignment

#### `computer founder brief`

Fetches founder mode briefing: open loops, pending decisions, household blockers, site anomalies.

```bash
python3 scripts/cli/computer.py founder brief
```

---

#### `computer founder load`

Prints the `decision_load_index` = `open_decisions × avg_decision_age / decisions_resolved_per_day`.

```bash
python3 scripts/cli/computer.py founder load
```

Rising index = founder mode accumulating debt, not burning it down.

---

#### `computer policy diff`

Compares current policy set vs last saved checkpoint. Highlights changed thresholds and tier assignments.

```bash
python3 scripts/cli/computer.py policy diff
python3 scripts/cli/computer.py policy diff --save    # save current as checkpoint
```

---

#### `computer trust report [--period 7d]`

Aggregates all 11 Trust KPIs for the given time window.

```bash
python3 scripts/cli/computer.py trust report
python3 scripts/cli/computer.py trust report --period 30d
```

KPIs reported: `suggestion_acceptance_rate`, `interrupt_dismissal_rate`, `correction_rate`, `approval_latency_p50/p95`, `override_rate`, `loop_closure_rate`, `privacy_incident_count`, `clarification_rate`, `regret_rate`, `spoken_regret_rate`, `decision_load_index`.

---

#### `computer shadow review`

Lists divergences from `eval-runner /eval/shadow/divergences`. Shows live vs shadow policy disagreements.

```bash
python3 scripts/cli/computer.py shadow review
```

---

#### `computer tool audit`

Verifies all registered MCP tools still match tier/mode/auth constraints per `tool-admission-policy.md`.

```bash
python3 scripts/cli/computer.py tool audit
```

---

#### `computer tool prune`

Lists tools eligible for deprecation or removal per `tool-lifecycle-policy.md`. Dry-run by default.

```bash
python3 scripts/cli/computer.py tool prune
```

---

#### `computer drift digest [--period 7d]`

Summarizes all drift events, overrides used, unresolved anomalies, and recommended actions.

```bash
python3 scripts/cli/computer.py drift digest
python3 scripts/cli/computer.py drift digest --period 30d
```

> **Weekly ritual:** Run `computer drift digest --period 7d` every Monday. Without this ritual, drift alerts decay into ignored logs.

---

#### `computer summarize <trace_id>`

One-line decision summary: key factors, confidence + cost, and validation signal.

```bash
python3 scripts/cli/computer.py summarize tr-abc123
```

Output format: `[trace_id]  DECISION  |  conf=0.82  |  factor=0.7, factor2=0.5  |  validated ✓`

---

#### `computer expectation capture`

Interactive prompt that records an `ExpectationDelta` when a user corrects or overrides the system.

```bash
python3 scripts/cli/computer.py expect
```

Prompts for: trace ID, what the user expected, what the system did, correction type. Writes to `packages/eval-fixtures/eval_fixtures/expectation_deltas.jsonl`.

---

## Taskfile Tasks

Run with `task <task-name>`.

### Development

| Task | Description |
|------|-------------|
| `task dev:all` | Start all services |
| `task dev:core` | Start core services (runtime-kernel, authz, memory, attention) |
| `task dev:family-web` | Start family-web with hot reload |
| `task dev:ops-web` | Start ops-web with hot reload |
| `task dev:workflow-runtime` | Start Temporal worker and API |

### Testing

| Task | Description |
|------|-------------|
| `task test:all` | Run all unit and integration tests |
| `task test:calibration` | Run calibration and drift monitor tests |
| `task test:long-horizon` | Run memory pressure and long-horizon tests |
| `task ci:full` | Full CI run (lint + type-check + tests + rubric) |
| `task ci:milestone-5` | Rover mission integration test suite |

### Simulation

| Task | Description |
|------|-------------|
| `task sim:up` | Start SITL environment |
| `task sim:socials` | Run social SITL scenarios |
| `task sim:scenarios` | Run site-control SITL scenarios |

### CLI Shortcuts

| Task | Equivalent command |
|------|-------------------|
| `task cli:doctor` | `computer doctor` |
| `task cli:trace` | `computer trace` |
| `task cli:explain` | `computer explain` |
| `task cli:drift` | `computer drift digest --period 7d` |
| `task cli:trust` | `computer trust report` |
| `task cli:brief` | `computer founder brief` |
| `task cli:tools` | `computer tool audit` |

### Release

| Task | Description |
|------|-------------|
| `task release:validate` | Run release-class validator |
| `task release:rubric` | Run perfection rubric (246/246 checks) |

---

## Utility Scripts

### `scripts/perfection_rubric.py`

Executable pass/fail rubric — 246 checks across all system domains.

```bash
python3 scripts/perfection_rubric.py
```

Categories: `runtime_v2`, `architecture`, `ai_safety`, `ux`, `release`, `recovery`, `simulation`, `hardware`, `boundary`, `observability`, `docs`, `scientific_rigor`, `v4_operational`.

### `scripts/generate_docs_index.py`

Regenerates `docs/README.md` from the current state of all docs.

```bash
python3 scripts/generate_docs_index.py
```

### `run_scenario.sh`

Runs named system scenarios for end-to-end validation.

```bash
./run_scenario.sh family_dinner
./run_scenario.sh emergency_escalation
./run_scenario.sh founder_deep_work
./run_scenario.sh greenhouse_anomaly
./run_scenario.sh privacy_ambiguity
./run_scenario.sh irrigation_anomaly
./run_scenario.sh site_security_alert
```
