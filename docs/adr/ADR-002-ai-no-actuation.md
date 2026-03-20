# ADR-002: AI cannot directly actuate hardware

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Computer uses an LLM (model-router, Ollama/vLLM) for advisory functions. LLMs are non-deterministic, subject to hallucinations, and cannot be fully audited at runtime. If AI can directly actuate hardware (open valves, start pumps, control drones), a hallucinated or adversarially prompted response could cause physical damage.

## Decision

AI (model-router, all LLM inference paths) cannot directly actuate hardware. The only permitted path from AI to physical action is:

```
model-router → assistant-tools → control-api → orchestrator → control service → device
```

This path includes: policy evaluation, risk class check, approval requirement, and audit logging.

## Enforcement

This decision is enforced by:
1. **CI safety gate**: Static analysis verifies no MQTT publish from any file under `apps/model-router/` or `apps/assistant-api/`.
2. **Architecture fitness function F01**: Tested on every PR.
3. **Tool registry**: T5 actions are not registered; model cannot call what does not exist.
4. **Orchestrator**: Even if control-api receives an AI-originated job proposal, the orchestrator evaluates risk class and approval requirements before dispatching.

## Allowed AI behaviors

- Summarize events and logs
- Propose jobs (as job proposals in the approval queue, not executed immediately)
- Rank remediation options for operator review
- Generate operator briefings
- Choose among pre-approved workflow templates

## Consequences

- AI is advisory only. This is intentional.
- Operator must approve any AI-proposed physical action above LOW risk class.
- System is safer but requires an active operator for significant site changes.
- This constraint is non-negotiable. Removing it requires a new ADR with explicit safety analysis.
