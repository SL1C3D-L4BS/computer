# ADR-020: Attention Plane — Delivery Decisions in Execution, Not UI

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Notification fatigue and inconsistent interrupt behavior occur when each UI component decides when to notify the user. This creates uncoordinated alert storms.

## Decision
Attention decisions are part of the CRK execution loop (step 9), not a UI concern. `services/attention-engine/` computes `INTERRUPT|QUEUE|DIGEST|SILENT` for every response using the scoring formula: `score = urgency × (1 - attention_load) × privacy_factor × time_weight`.

CRITICAL risk class always overrides to INTERRUPT.

## Consequences
- Consistent interrupt behavior regardless of surface
- Centralized attention load tracking in `ComputerState`
- If attention-engine unreachable → fallback to QUEUE NORMAL (never halt loop)
