# ADR-023: AI Evaluation Plane — Behavioral Regression Gate

**Status:** Accepted  
**Date:** 2026-03-19

## Context
AI model updates, prompt changes, and context-router logic changes can introduce behavioral regressions that structural tests do not catch. "Tests pass" does not mean "AI still respects ADR-002."

## Decision
`services/eval-runner/` runs a labeled fixture corpus (`packages/eval-fixtures/`) against the live `runtime-kernel`. The `eval:regression` CI gate blocks deployment if any P0/P1 fixture regresses. P0 categories: `no_actuation_violation`, `privacy_leakage`, `wrong_memory_scope`.

## Consequences
- AI quality regressions are caught before production
- Eval corpus grows with each discovered regression
- Full eval run required for: new AI model, prompt change, context-router logic change
