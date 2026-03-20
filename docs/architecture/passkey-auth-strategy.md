# Passkey Authentication Strategy — family-web

**Status:** Active  
**ADR:** ADR-034  
**Version:** 1.0.0

---

## Overview

Passkeys (WebAuthn/FIDO2) provide hardware-bound, phishing-resistant authentication for `family-web`. In the V4 two-track auth model, passkeys are the **mandatory mechanism for the approval track**.

Passkeys are not a login convenience. They are an escalation gate for sensitive operations.

---

## Two-Tier Trust Model (explicit split per V4 plan)

| Track              | Trigger                                                       | Auth mechanism          | Session duration      |
| ------------------ | ------------------------------------------------------------- | ----------------------- | --------------------- |
| **Session track**  | Login, browsing, normal household queries                     | OAuth 2.1 session token | 24h rolling           |
| **Approval track** | Sensitive approvals, memory export, policy changes, recovery  | Passkey WebAuthn ceremony | Per-action (no cache) |

The approval track is invoked **per action**, not per session. A valid session token does not grant approval-track access. The passkey ceremony must complete immediately before each approval-track operation.

---

## Approval-Track Operations (require passkey re-auth)

- Publishing policy changes (`policy-publish-gate.md`)
- Exporting personal memory or household data
- Identity recovery and new device trust enrollment
- Completing an `approval_request` in the `approvals.pending` tool
- `decisions.register` calls with `risk_class=HIGH`

---

## WebAuthn Registration Flow

```
1. User navigates to /auth/register
2. family-web requests a registration challenge from identity-service
   POST /identity/passkey/register/begin → { challenge, rp, user, pubKeyCredParams }
3. Browser creates credential via navigator.credentials.create()
4. family-web sends credential attestation to identity-service
   POST /identity/passkey/register/complete → { credential_id, public_key, device_id }
5. identity-service stores: { user_id, credential_id, public_key, device_id, created_at }
6. OpenFGA tuple written: device:<device_id> trusted_by user:<user_id>
```

---

## WebAuthn Authentication Flow (Session Track)

```
1. User navigates to /auth/login
2. family-web requests assertion challenge
   POST /identity/passkey/auth/begin → { challenge, allowCredentials }
3. Browser signs challenge via navigator.credentials.get()
4. family-web sends assertion to identity-service
   POST /identity/passkey/auth/complete → { session_token, expires_at }
5. Session token stored in HttpOnly cookie; used for session-track requests
```

---

## WebAuthn Re-auth Flow (Approval Track)

```
1. User attempts approval-track action (e.g., publish policy)
2. family-web detects approval_track_required=true in API response (HTTP 403)
3. Approval prompt shown; user initiates passkey ceremony
4. Fresh assertion challenge generated (one-time, bound to action)
   POST /identity/passkey/approval/begin → { challenge, action_context }
5. Browser signs; assertion sent with original request
   POST /identity/passkey/approval/complete + original_request → approval_token
6. Original action retried with approval_token in Authorization header
7. authz-service verifies approval_token → OpenFGA tuple: approval_track_verified
```

Key properties:
- Approval tokens are **single-use** and **action-bound** (contain action hash)
- No caching: every approval-track operation requires a fresh ceremony
- Fallback: existing session tokens remain valid for session-track; no fallback to passwords

---

## Origin Binding

family-web is the only valid origin for passkey ceremonies. The `rpId` must match the deployed family-web domain. Localhost binding is permitted in development only.

```
rpId: family.homestead.local   (production)
rpId: localhost                (development only)
```

Cross-origin passkey sharing is not supported.

---

## Integration with identity-service

- Passkey registration and authentication endpoints: `services/identity-service/`
- Public key stored in Postgres: `identity.passkey_credentials(credential_id, user_id, public_key_cose, sign_count, device_id)`
- Approval tokens signed by identity-service, verified by authz-service

---

## Stub Implementation

Stub passkey pages are located at:
- `apps/family-web/src/app/auth/register/page.tsx`
- `apps/family-web/src/app/auth/login/page.tsx`

These stubs define the component structure and API call shape; they call `identity-service` which itself is currently stubbed.

---

## Fallback Behavior

- If identity-service is unreachable: approval-track operations are **blocked**, not degraded
- Session-track operations continue with existing session tokens
- No silent fallback to passwords or magic links for approval-track

See also:
- `docs/architecture/rebac-auth-evolution.md`
- `docs/adr/ADR-034-passkey-first-auth-family-web.md`
