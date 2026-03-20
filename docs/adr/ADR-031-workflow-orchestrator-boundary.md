# ADR-031: workflow-runtime ↔ orchestrator Boundary Contract

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Without an explicit boundary contract, `workflow-runtime` and `orchestrator` will accumulate hidden coupling (direct DB calls, shared state, MQTT from workflow code) that produces subtle failures.

## Decision
The boundary is governed by `docs/architecture/workflow-orchestrator-boundary.md`.

NEVER rules (P0 violations):
- `workflow-runtime` MUST NOT publish to MQTT directly
- `workflow-runtime` MUST NOT modify orchestrator job state (no DB writes)
- `orchestrator` MUST NOT create or cancel Temporal workflows
- Neither MUST call the other's internal database

Permitted: WR creates jobs via control-api; ORC signals WR via Temporal signal.

## Consequences
- Violation of any NEVER rule is a P0 architectural bug — revert immediately
- Cross-boundary communication is always via HTTP API or Temporal signal
- Both engines can evolve independently within their authority boundaries
