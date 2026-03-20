# ADR-035: Local-First Sync Scope and Device-Trust Prerequisites

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Founder  

---

## Context

`family-web` users need offline access to household data. However, not all household data is safe or appropriate to cache locally. Work memory, site state, and personal memory require careful handling to avoid privacy violations and stale-state actuation risks.

## Decision

Implement local-first sync for `family-web` using PGlite and Automerge CRDTs, but with **strict scope discipline**:

**In scope (local-first allowed):**
- Shopping lists (Automerge CRDT, collaborative)
- Chore assignments (Automerge CRDT, collaborative)
- Reminder history (PGlite read cache)
- Approvals queue cache (PGlite read-only cache; viewing only)
- Household dashboard snapshots (PGlite stale-while-revalidate)

**Out of scope (network-required):**
- Work memory, decision register, founder loops
- Raw site-control state (sensor readings, job queues)
- Personal memory cross-device sync without explicit device-trust story
- Any approval-track operations

**Conflict resolution:** Explicit user statement always wins over automated inference. User-initiated deletes win over concurrent adds.

## Consequences

**Positive:**
- Household UI remains usable during network outages
- Shopping and chore editing is collaborative and conflict-free
- Clear scope prevents accidental offline access to sensitive data

**Negative:**
- PGlite adds initial page load cost (WASM bundle)
- Automerge changeset sync requires a sync server (stub in V4; production in V5)
- Scope boundaries must be enforced by convention (no runtime enforcement at this stage)

## Prerequisites Not Yet Implemented

- Personal memory cross-device sync requires device-trust enrollment (ADR-034) — deferred to V5
- Full Automerge sync server — stubbed in V4; full implementation in V5

See also: `docs/architecture/local-first-sync-strategy.md`
