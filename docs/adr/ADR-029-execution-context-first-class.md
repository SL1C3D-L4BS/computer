# ADR-029: ExecutionContext is First-Class and Audited at Every Step

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Without a single threaded context object, each CRK step receives different slices of information, making it impossible to reconstruct the full picture of a request during incident investigation.

## Decision
`ExecutionContext` (from `packages/runtime-contracts/models.py`) is the single object threaded through all 10 CRK steps. It is enriched at each step (never replaced mid-loop). A `StepAuditRecord` is written at every step transition, forming an immutable audit chain. `trace_id` in `ExecutionContext` must match `trace_id` in `ResponseEnvelope`.

## Consequences
- Every request has a complete, reconstructible audit chain
- `trace_id` is a first-class operational invariant (checked by rubric)
- `mode_change_reason` is required whenever mode changes from surface default
