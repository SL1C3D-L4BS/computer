# ReBAC Authorization Evolution Strategy

**Status:** Active  
**ADR:** ADR-033  
**Version:** 1.0.0

---

## Overview

This document defines the migration path from RBAC v1 (current) to Relationship-Based Access Control (ReBAC) v2 using OpenFGA (Zanzibar-style authorization).

The key architectural addition in V4 is an **explicit two-track auth model**: session auth and approval auth are different tracks with different mechanisms, not just different roles.

---

## Two-Track Auth Model

This split must be understood and implemented clearly. Authentication is not monolithic.

| Track              | Purpose                                                                      | Auth mechanism                          |
| ------------------ | ---------------------------------------------------------------------------- | --------------------------------------- |
| **Session track**  | Identity, browsing, normal household usage, routine queries                  | Standard OAuth 2.1 session token        |
| **Approval track** | Sensitive approvals, memory export, policy changes, identity recovery        | Passkey re-auth (WebAuthn ceremony)     |

**Passkeys dominate the approval track.** They are not a login convenience — they are an escalation gate. A session token alone is insufficient for approval-track operations.

Operations requiring approval-track auth:
- Publishing a policy change (`policy-publish-gate.md`)
- Exporting personal memory or household data
- Identity recovery and device trust changes
- Sensitive approvals from `approvals.pending`
- Registering a high-stakes decision via `decisions.register` with `risk_class=HIGH`

---

## Current State: RBAC v1

The existing `authz-service` enforces role-based access with scope-based policies:

```
user:founder → roles: [operator, resident, owner]
user:family_member → roles: [resident]
user:guest → roles: [guest]
```

Limitations:
- Roles are flat; cannot model relationships like "family member of household X"
- No context-aware authorization (mode, device trust, approval track)
- No tuple-based relationship queries (Zanzibar-style)
- Cannot model "A can see B's shared note but not B's private note"

---

## Target State: ReBAC v2 (OpenFGA)

OpenFGA models authorization as a **relationship graph**. Instead of "does user X have role Y?", we ask "does user X have relation R to resource Z?"

### Domain Types and Relations

```
type user
type household
  relations
    define resident: [user]
    define owner: [user]
    define guest: [user] but not resident

type memory_entry
  relations
    define owner: [user]
    define shared_with: [user, household#resident]
    define can_read: owner or shared_with
    define can_delete: owner

type policy
  relations
    define author: [user]
    define can_publish: author and approval_track_verified

type device
  relations
    define trusted_by: [user]
    define approval_track_capable: trusted_by
```

### Key Tuples

```
user:founder    member    household:main
user:spouse     resident  household:main
user:child      resident  household:main
user:founder    operator  site:homestead
user:founder    owner     memory_entry:*  (scope-level)
```

---

## Migration Path

### Phase 1 (current): RBAC v1 + Scopes
- `authz-service` enforces role membership + scope strings
- All authorization decisions logged as `InvariantCheckResult`

### Phase 2 (V4 target): Hybrid RBAC + OpenFGA queries
- New authorization paths (memory sharing, policy publishing) go through OpenFGA
- Existing role checks remain in `authz-service`
- OpenFGA stub schema deployed at `packages/authz-model/openfga_schema.fga`
- Approval track implemented as a context condition in OpenFGA policy

### Phase 3 (V5): Full ReBAC
- All authorization migrated to OpenFGA
- RBAC v1 retired
- Device-trust context fed into tuple store

---

## OpenFGA Schema Location

`packages/authz-model/openfga_schema.fga` — stub defining all types, relations, and conditions.

See also:
- `docs/architecture/passkey-auth-strategy.md`
- `docs/adr/ADR-033-rebac-authorization-evolution.md`
- `docs/adr/ADR-034-passkey-first-auth-family-web.md`
