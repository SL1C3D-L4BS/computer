# Local-First Sync Strategy — family-web

**Status:** Active  
**ADR:** ADR-035  
**Version:** 1.0.0

---

## Overview

`family-web` surfaces must remain usable during network outages. This document defines the local-first strategy for household data using PGlite (embeddable Postgres in the browser) and Automerge CRDTs for conflict-free collaborative state.

---

## Scope Discipline (strict — enforced by rubric)

Local-first sync applies **only** to:

| Data type                  | Sync model                   | Notes                                    |
| -------------------------- | ---------------------------- | ---------------------------------------- |
| Shopping lists             | Automerge CRDT               | Collaborative across household devices   |
| Chore assignments          | Automerge CRDT               | Last-explicit-user-statement wins        |
| Reminder history           | PGlite read cache            | Read-only offline; sync on reconnect     |
| Approvals queue cache      | PGlite read cache (read-only)| Can view pending approvals offline; cannot approve offline |
| Household dashboard snapshots | PGlite read cache         | Stale-while-revalidate pattern           |

**Does NOT apply to:**

- Work memory, decision register, founder loops
- Raw site-control state (sensor readings, job queues)
- Personal memory across devices without explicit device-trust story (ADR-034)
- Any data requiring approval-track auth to access

This scope is intentional and non-negotiable. Expanding local-first to work memory or site state requires a separate ADR with a device-trust story.

---

## Architecture

### PGlite (embeddable Postgres)

PGlite runs a full Postgres engine in the browser via WASM. Benefits:
- SQL queries on local data (same query interface as the server)
- Structured data with schema enforcement
- Suitable for read caches: data synced from server, queried locally

Usage in family-web:
- `lib/local-db.ts` — PGlite instance, schema initialization, migration runner
- Tables: `reminders_cache`, `approvals_cache`, `dashboard_snapshots`

### Automerge CRDTs (collaborative household data)

Automerge provides conflict-free replicated data types. Used for data that multiple household members edit simultaneously.

Usage:
- `packages/sync-model/src/crdt-types.ts` — CRDT-compatible type definitions
- Shopping lists: `AutomergeMap<string, ShoppingItem>` where key is item identifier
- Chore assignments: `AutomergeList<ChoreAssignment>`

### Conflict Resolution Policy

Explicit user statement always wins over automated inference:
1. If two devices both modify the same shopping item, last-write-wins within Automerge merge
2. If a user explicitly deletes an item while another device adds it, explicit delete from the user who deleted wins
3. Automated system suggestions (e.g., auto-generated shopping items) lose to any human edit

---

## Offline Capability Targets

| Operation                      | Offline behavior             | Sync on reconnect              |
| ------------------------------ | ---------------------------- | ------------------------------ |
| View shopping list             | ✓ Full offline from PGlite   | Merge Automerge changes        |
| Edit shopping list             | ✓ Local CRDT edit            | Push Automerge changeset       |
| View chore assignments         | ✓ Full offline from PGlite   | Merge Automerge changes        |
| View pending approvals         | ✓ Read-only cache            | Refresh (cannot approve offline) |
| View household dashboard       | ✓ Stale snapshot             | Invalidate + reload            |
| Submit approval                | ✗ Requires network + passkey | N/A                            |
| Access work memory             | ✗ Not local-first            | N/A                            |

---

## Offline-Aware Fetch Pattern

`apps/family-web/src/lib/api.ts` implements stale-while-revalidate for scoped offline data:

```typescript
// For in-scope offline data: try PGlite cache first, revalidate in background
async function offlineFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T>

// For out-of-scope data: network-only; throws on offline
async function requiresNetwork<T>(fetcher: () => Promise<T>): Promise<T>
```

This ensures work memory and site state always reflect server truth.

---

## Device Trust Prerequisites

Personal memory sync across multiple devices requires an explicit device-trust story (ADR-034). Until a device is enrolled via passkey registration, it cannot access personal memory entries. Household data (shopping, chores, reminders) does not require device-trust enrollment — any authenticated household member can access it.

---

## ADR-035

See `docs/adr/ADR-035-local-first-sync-scope.md` for the formal decision record.
