# ADR-006: Safety gates are required for all high-risk commands

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Physical systems can cause irreversible damage if commanded incorrectly: flooded zones, overfed crops, frozen plants, crashed robots. The system needs a consistent mechanism to prevent reckless actuation.

## Decision

All commands with `risk_class >= HIGH` require an explicit safety gate before execution. The gate is enforced by the orchestrator and is not bypassable through any software path.

Safety gate requirements for HIGH and CRITICAL:
1. The job must have a logged approval event (operator action in ops-web).
2. All job preconditions must be evaluated and satisfied.
3. No conflicting job in EXECUTING state for the same asset.
4. Control service must be healthy (health check passes).
5. Emergency mode approval rules apply separately (see emergency-mode-spec.md).

## Enforcement

- **CI safety gate**: Tests that any job with `risk_class=HIGH` and `approval_mode=AUTO` raises `PolicyViolationError`.
- **Architecture fitness function F05**: Tested on every PR.
- **Orchestrator state machine**: `VALIDATING` state performs all pre-execution checks; job cannot reach `APPROVED` without passing them.

## Consequences

- HIGH and CRITICAL commands always require human action (unless auto-approved by sensor_rule for predefined emergency scenarios).
- The ops-web command approval UI must clearly show risk_class, affected assets, preconditions, and rollback plan.
- AI-originated jobs with risk_class >= MEDIUM always require operator review (even if policy would otherwise auto-approve).
- Operators are never blind to what they are approving.
