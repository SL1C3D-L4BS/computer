# runtime-contracts

> Canonical Python type definitions for the Computer Runtime Kernel: all typed decision objects, scientific model types, and V4 policy types.

---

## Overview

`runtime-contracts` is the **single source of truth for all CRK data types**. Every service that participates in the Computer runtime imports from this package. No service defines its own execution types locally.

This package implements the scientific control-system model: typed uncertainty, explicit objectives, named invariants, and proof obligations.

## Responsibilities

- Define all canonical Python dataclasses for CRK execution
- Provide typed scientific model objects: `ConfidenceScore`, `UncertaintyVector`, `TrustSignal`
- Define V4 policy types: `PolicyImpactReport`, `ExpectationDelta`
- Provide no runtime logic; this is a pure type/schema package

**Must NOT:**
- Contain business logic
- Import from application services
- Define database models (those live in service repositories)

## Type Catalog

### Execution types

| Type | Description |
|------|-------------|
| `ExecutionContext` | Full request context passed through all 10 CRK steps |
| `ControlAction` | Output of step 6–7: what Computer will do |
| `DecisionRationale` | Typed explanation of why a decision was made |
| `AttentionDecision` | INTERRUPT / DIGEST / SUPPRESS / DEFER decision |
| `AttentionCost` | Computed attention cost for interrupt evaluation |

### Scientific model types

| Type | Description |
|------|-------------|
| `ConfidenceScore` | Calibrated belief value [0, 1] with source |
| `UncertaintyVector` | Named uncertainty dimensions |
| `TrustSignal` | Observation that updates trust state |
| `StateEstimate` | Estimated system state with confidence |
| `ObservationRecord` | Typed audit record for all observable events |
| `InvariantCheckResult` | Pass/fail for a named safety invariant |

### Memory types

| Type | Description |
|------|-------------|
| `OpenLoop` | Active unresolved commitment or task |
| `Commitment` | Explicit promise to complete an action |
| `FollowUp` | Scheduled check on previous interaction |

### V4 policy types

| Type | Description |
|------|-------------|
| `PolicyImpactReport` | Operator declaration of expected policy change impact (required before replay) |
| `ExpectationDelta` | Human correction captured when user overrides/redirects system |

## Interfaces

This is a pure library. Import directly:

```python
from runtime_contracts.models import (
    ExecutionContext,
    ControlAction,
    DecisionRationale,
    ConfidenceScore,
    PolicyImpactReport,
    ExpectationDelta,
)
```

## Dependencies

### External

| Library | Why |
|---------|-----|
| `dataclasses` | Core Python stdlib; no external runtime deps |

## Local Development

```bash
cd packages/runtime-contracts
pip install -e .
```

## Testing

```bash
pytest packages/runtime-contracts/tests/ -v
```

## Observability

- Type-only package; no runtime telemetry
- Schema changes should be reflected in ADR or PR description

## Security / Policy

- `PolicyImpactReport` is immutable once filed; no update path
- `ExpectationDelta` records are append-only in eval fixture store
