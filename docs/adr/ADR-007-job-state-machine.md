# ADR-007: All workflows are job/state-machine driven

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Without a formal job model, physical operations become a tangle of ad-hoc function calls with no audit trail, no rollback, and no consistent failure handling. This is unacceptable for a safety-critical system.

## Decision

Every physical operation in Computer is a **Job** with an explicit state machine. There is no ad-hoc execution outside of the job model.

### Job state machine

```
PENDING → VALIDATING → APPROVED → EXECUTING → COMPLETED
                    ↓           ↓           ↓
                 REJECTED    REJECTED     FAILED
                                          ABORTED
```

### State transition rules

| From | To | Guard |
|------|----|-------|
| PENDING | VALIDATING | Job submitted to orchestrator |
| VALIDATING | APPROVED | All preconditions satisfied; approval obtained |
| VALIDATING | REJECTED | Precondition failed; policy rejected |
| APPROVED | EXECUTING | Command dispatch initiated |
| APPROVED | REJECTED | Operator rejects in approval queue |
| EXECUTING | COMPLETED | All steps completed; command-ack received |
| EXECUTING | FAILED | Command-ack timeout; control service error |
| EXECUTING | ABORTED | Abort condition triggered; E-stop received |
| Any | ABORTED | Emergency E-stop command |

### Mandatory job fields

Every job must have:
- `job_id`: UUID
- `type`: Job type from allowed types registry
- `requested_by`: user_id or service_id
- `origin`: `operator` | `policy` | `ai_advisory` | `sensor_rule` | `emergency`
- `target_asset_ids`: list of affected asset IDs (no vendor entity names)
- `risk_class`: from command-risk-classification.md
- `approval_mode`: derived from origin × risk_class policy
- `state`: current state
- `command_log`: list of logged dispatch/ack events
- `created_at`, `updated_at`, `completed_at`

## Consequences

- Every physical action is traceable: who requested it, why, what happened.
- Rollback and recovery are well-defined per state.
- audit-gate CI test verifies command_log is written before EXECUTING state.
- CrewAI or agent frameworks, if used, must create jobs through the orchestrator API — never actuate directly.
- Ad-hoc MQTT publish for control purposes is a CI safety gate violation.
