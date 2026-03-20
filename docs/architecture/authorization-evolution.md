# Authorization Evolution

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-019 (Authorization Evolution)  
**Service:** `services/authz-service/`  
**Package (v2):** `packages/authz-model/`

---

## v1: RBAC (current)

Role-Based Access Control with named policy rules. Simple, predictable, easy to audit.

### Scope Grid

| Role | PERSONAL | HOUSEHOLD_SHARED | WORK | SITE | Emergency |
|------|----------|-----------------|------|------|-----------|
| Founder/Owner | ✓ | ✓ | ✓ | ✓ | ✓ |
| Adult member | ✓ | ✓ | ✗ | ✗ | limited |
| Teen | ✓ (own only) | ✓ (read) | ✗ | ✗ | ✗ |
| Child | ✗ | ✓ (read) | ✗ | ✗ | ✗ |
| Guest | ✗ | ✓ (read, limited) | ✗ | ✗ | ✗ |
| Contractor | ✗ | ✗ | scoped | scoped | ✗ |

### v1 Policy Rules (in evaluation order)

1. **Emergency restriction**: EMERGENCY mode allows only `emergency.*` resources
2. **AI_ADVISORY approve guard**: AI cannot approve HIGH/CRITICAL risk jobs (ADR-002, F05)
3. **AI_ADVISORY site guard**: AI cannot create `site_control.*` resources
4. **FAMILY isolation**: FAMILY mode cannot access `personal.*`, `work.*`
5. **PERSONAL site guard**: PERSONAL mode cannot access `site_control.*`
6. **Default allow** (v1 permissive)

---

## v2: ReBAC (planned)

Relationship-Based Access Control. Enables household-specific access patterns that RBAC cannot express.

### Why ReBAC

RBAC cannot express:
- "Alice temporarily shares greenhouse access with contractor Bob for this week"
- "The Saturday garden workflow can run, but only if the irrigation schedule was confirmed today"
- "Guest Carol can access the shared shopping list but not Alice's personal lists"

ReBAC models these as **relationships** between subjects, resources, and conditions.

### Relationship Model

```
User --[owner]--> Household
User --[member]--> Household
User --[guest]--> Household (time-limited)

User --[admin]--> Resource
User --[viewer]--> Resource
User --[shared_with]--> Resource (time-limited, revocable)

Resource --[child_of]--> Resource  # inheritance
```

### v2 AuthzRequest

```python
@dataclass
class AuthzRequest:
    subject: str      # User or service ID
    resource: str     # Resource identifier
    action: str       # read | write | invoke | create | approve | delete

    # Full context — required (from runtime-contracts)
    context: AuthzContext  # mode, risk_class, origin, location, time_of_day
```

**Mode is REQUIRED in every request.** The same user in PERSONAL vs SITE mode has different access.

---

## Policy Function (not ordering)

```python
# WRONG — do not compare as numbers:
if user.role >= resource.required_role:  # ← never
    allow()

# CORRECT — named policy function:
def evaluate(subject: str, resource: str, action: str, context: AuthzContext) -> AuthzResponse:
    # Evaluate named rules in priority order
    # Return first matching rule outcome
    ...
```

**Why:** `risk_class` and trust tier are different axes. A request with `risk_class=HIGH` does not automatically grant access to all resources. A SITE-mode request doesn't bypass EMERGENCY restrictions. Named rules make the logic auditable and testable.

---

## Token Audience Binding (RFC 8707)

Every token issued by the Computer authorization server must bind its audience to a specific resource server URI.

```python
# Token payload
{
    "sub": "founder_001",
    "aud": ["http://computer.local/api/control"],  # Must match target resource URI
    "scope": "site:read site:control",
    "exp": 1742000000,
    "iat": 1741996400
}
```

**Enforcement in authz-service:**
```python
def validate_token_audience(token: dict, expected_resource_uri: str) -> bool:
    aud = token.get("aud", [])
    if isinstance(aud, str):
        aud = [aud]
    return expected_resource_uri in aud
```

If audience doesn't match → deny. This prevents token replay attacks across services.

---

## Why Mode Is in AuthzContext

A user may have different access rights depending on their current operating mode:

| Same user, different mode | Access |
|--------------------------|--------|
| `founder_001` in PERSONAL mode | personal tools, personal memory |
| `founder_001` in FAMILY mode | household tools, shared memory |
| `founder_001` in SITE mode | all tools including T3/T4, site-control |
| `founder_001` in EMERGENCY | emergency tools only |

Mode is **not a preference** — it is an authorization dimension. Two requests from the same user with the same action but different modes may get different outcomes. This is by design.

---

## Migration Path: v1 → v2

| Phase | Action |
|-------|--------|
| v1 (current) | RBAC policy function in `authz_service/main.py` |
| v1.5 | Add `authz-model` package with relationship graph types |
| v2 | Deploy ReBAC engine; migrate rules from v1 to v2 one-by-one |
| v2 stable | Deprecate v1 rules; all checks via ReBAC |

The `AuthzRequest` interface does not change between v1 and v2.  
Only the evaluation engine inside `authz-service` changes.
