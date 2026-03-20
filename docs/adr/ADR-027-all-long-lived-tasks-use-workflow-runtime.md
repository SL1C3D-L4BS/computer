# ADR-027: All Long-Lived Tasks Must Use workflow-runtime

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Long-running HTTP call sequences, cron jobs, and ad-hoc polling loops accumulated as "implicit workflows" that approximate workflow behavior without fault-tolerance guarantees.

## Decision
Any task spanning more than one user interaction, more than one service call, or more than 30 seconds of wall-clock time is a durable workflow. It must use `services/workflow-runtime/` (Temporal). No exceptions. No "I'll just poll every minute" workarounds.

## Consequences
- No implicit workflows in the codebase
- All multi-step sequences survive server restarts
- Temporal history provides full replay capability for debugging
