# ADR-028: Attention Decisions Are Part of Execution Step 9, Not UI

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Each UI component was independently deciding when to notify the user, producing uncoordinated alerts and inconsistent behavior across surfaces.

## Decision
`attention-engine` at CRK step 9 owns all delivery decisions (INTERRUPT/QUEUE/DIGEST/SILENT). UI components receive the `AttentionDecision` and render accordingly — they do not decide. This is a runtime execution decision, not a presentation decision.

## Consequences
- Consistent interrupt behavior across all surfaces
- Attention load is tracked centrally in `ComputerState`
- UI components become simpler: render what they receive
- Step 9 failure → fallback to QUEUE NORMAL, never halt
