# ADR-017: Durable Workflow Plane

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Platform team

## Context
Multi-step household tasks (irrigation schedules, morning routines, approval workflows) must survive server restarts. Ad-hoc HTTP call sequences do not provide this guarantee.

## Decision
All long-lived, multi-step execution is managed by `services/workflow-runtime/` using the Temporal Python SDK. Task queue: `computer-main`.

## Consequences
- Single authoritative source for durable execution state
- Temporal history enables replay for debugging
- `asyncio.sleep()` in a workflow = durable timer (survives restart)
- Constraint: workflow-runtime MUST NOT publish to MQTT directly (see ADR-031)
