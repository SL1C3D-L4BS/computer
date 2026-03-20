# ADR-034: Passkey-First Authentication with Approval-Grade Escalation for family-web

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Founder  

---

## Context

`family-web` currently has no authentication implementation. Household members need to:
1. Access shared household data without password friction
2. Approve sensitive operations (memory export, policy changes) with escalated assurance
3. Recover identity if a device is lost

Passwords do not satisfy requirements 1 and 2 simultaneously. Magic links are phishable. Hardware tokens add friction.

## Decision

Implement **WebAuthn passkeys** as the primary authentication mechanism for `family-web`, with a **two-tier trust model**:

1. **Session track**: passkey ceremony produces a session token (OAuth 2.1 bearer token via identity-service); 24h rolling; suitable for all normal household operations
2. **Approval track**: passkey re-auth **per action** (no caching); required for: policy changes, memory export, sensitive approvals, device trust changes; produces a single-use action-bound approval token

Passkeys are not a login convenience. On the approval track, they are a **blocking gate**: no session token — however valid — bypasses the per-action ceremony.

## Consequences

**Positive:**
- Phishing-resistant by design (origin-bound)
- No passwords to compromise or rotate
- Approval track provides hardware-level assurance for policy changes
- Compatible with OpenFGA device-trust tuple (`device:<id> trusted_by user:<id>`)

**Negative:**
- Requires identity-service passkey endpoints (currently stubbed)
- Device loss requires recovery ceremony (fallback: other trusted device)
- Browser support: requires modern browser with WebAuthn Level 3 support
- No cross-origin passkey sharing (intentional, per origin binding)

## Fallback Behavior

- **Session track unavailable**: user must re-register on this device
- **Approval track unavailable** (identity-service down): approval-track operations are blocked; session-track operations continue
- **No silent fallback to passwords**: this is explicit and non-negotiable

## Origin Binding

```
rpId: family.homestead.local   (production)
rpId: localhost                (development only)
```

## Implementation

Stub pages:
- `apps/family-web/src/app/auth/register/page.tsx`
- `apps/family-web/src/app/auth/login/page.tsx`

Backend: `services/identity-service/` (passkey endpoints, stubbed)

See also: `docs/architecture/passkey-auth-strategy.md`, `ADR-033`
