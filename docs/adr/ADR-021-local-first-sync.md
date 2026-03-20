# ADR-021: Local-First Sync — family-web Resilience

**Status:** Accepted  
**Date:** 2026-03-19

## Context
`family-web` must remain functional when the homestead network is intermittently unavailable. Server-dependent state causes data loss during outages.

## Decision
`family-web` implements local-first sync using `packages/sync-model/` CRDT-compatible types. State is persisted locally (localStorage/IndexedDB) and synced on reconnect via context-router.

## Consequences
- family-web works offline for all common household tasks
- Conflicts resolved by CRDT operations or user prompt for irreconcilable cases
- Sync is eventually consistent — not real-time for offline state
