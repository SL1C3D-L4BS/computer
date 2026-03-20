# ADR-030: Kernel Authority Model — Non-Overlapping Component Ownership

**Status:** Accepted  
**Date:** 2026-03-19

## Context
`runtime-kernel` and `orchestrator` were accumulating overlapping authority through implementation entropy ("dual-kernel drift"), creating subtle bugs and unclear ownership of job state.

## Decision
A hard authority table (`docs/architecture/kernel-authority-model.md`) defines what each component owns and does NOT own. Any PR that moves authority across cells requires an ADR update. The critical non-overlap:
- `runtime-kernel` = request lifecycle kernel
- `orchestrator` = job/command execution engine

They do not overlap. They communicate via `control-api` job submission or internal job API.

## Consequences
- Drift is identifiable at code review time
- New components must declare their authority in README
- Structural rubric checks for key authority invariants (MQTT only from orchestrator, etc.)
