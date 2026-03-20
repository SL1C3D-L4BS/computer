# Architecture Fitness Functions

Fitness functions are **machine-checked** gates. They are not aspirations. Each maps to a specific CI gate that fails the pipeline if violated.

## Core fitness functions

### F01 — No direct actuator publish from AI paths

**Assertion**: No code path originating from model-router, assistant-api, context-router, or any LLM inference call may publish to MQTT command_request or command_ack topics.

**CI gate**: `safety-gate` — static analysis scans Python and TypeScript for MQTT publish calls in packages under `apps/model-router/`, `apps/assistant-api/`, `services/context-router/`. Any match fails the build.

**Allowed path**: model-router → assistant-tools → control-api (HTTP POST) → orchestrator → MQTT.

### F02 — No vendor entity names in core job logic

**Assertion**: Orchestrator and job schemas must not contain strings matching known vendor entity patterns (e.g., `switch.`, `light.`, `sensor.` HA entity prefixes, Frigate camera names, device UUIDs).

**CI gate**: `contract-gate` — schema linter checks `packages/contracts/` and `apps/orchestrator/` for vendor entity patterns.

**Allowed path**: adapters translate vendor names to canonical asset IDs. Orchestrator uses asset IDs only.

### F03 — No service without typed contracts

**Assertion**: Every app and service that exposes HTTP must have a corresponding schema in `packages/contracts/` or `packages/assistant-contracts/`. Schemas must be referenced in the service's README.

**CI gate**: `contract-gate` — checks that every service directory contains a `contracts.json` reference or import.

### F04 — No un-audited command path

**Assertion**: Every job that transitions to `EXECUTING` must produce a `command_log` entry in Postgres before dispatching to a control service.

**CI gate**: `audit-gate` — integration test runs an irrigation job and asserts `command_log` row exists before control service receives command.

### F05 — No high-risk workflow without explicit approval mode

**Assertion**: Every job with `risk_class >= HIGH` must have `approval_mode != AUTO`.

**CI gate**: `safety-gate` — pytest asserts on orchestrator state machine: any job with `risk_class=HIGH` or `risk_class=CRITICAL` and `approval_mode=AUTO` raises a PolicyViolationError.

### F06 — No release without rollback metadata

**Assertion**: Every release tag must include a `rollback_to` reference in the release manifest (`RELEASES.md` or equivalent).

**CI gate**: `release-gate` — release workflow checks for `rollback_to` field in release body before tagging.

### F07 — No robotics merge without sim pass

**Assertion**: Any PR touching `robotics/`, `services/rover-control/`, or `services/drone-control/` must pass the simulation gate before merging.

**CI gate**: `robotics-gate` — required status check on PRs matching path patterns `robotics/**`, `services/rover-control/**`, `services/drone-control/**`.

### F08 — No hardware deploy without restore-tested backup state

**Assertion**: Release to production must include a completed backup verification step. Backup verification runs a restore dry-run against the latest backup and records the result.

**CI gate**: `release-gate` — release workflow requires a `backup-verified: true` attestation from the backup-restore check job.

## Enforcement mechanism

Fitness functions are enforced in CI via GitHub Actions (or equivalent) required status checks. No PR may merge without passing all applicable gates.

Gate-to-fitness-function mapping:

| CI gate | Fitness functions |
|---------|------------------|
| `contract-gate` | F02, F03 |
| `safety-gate` | F01, F05 |
| `audit-gate` | F04 |
| `robotics-gate` | F07 |
| `release-gate` | F06, F08 |

## Fitness function registry

Fitness functions are versioned in this document. Adding a new function requires:
1. Adding an entry here with assertion and CI gate.
2. Adding the CI gate job to `.github/workflows/`.
3. Adding a test or static analysis rule that implements the assertion.
4. PR review from a FOUNDER_ADMIN.

Removing a fitness function is not permitted without an ADR.
