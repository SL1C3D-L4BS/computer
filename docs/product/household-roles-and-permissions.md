# Household Roles and Permissions

Defines the role model for household members and how roles map to assistant and ops permissions.

## Role definitions

| Role | Description | Who holds it |
|------|-------------|-------------|
| `FOUNDER_ADMIN` | Full ops + full assistant + approval authority | Site owner; typically one person |
| `ADULT_MEMBER` | Full household assistant; limited site access | Adult household members |
| `CHILD_GUEST` | Conversational assistant only; no sensitive memory; no site or control access | Children, guests |
| `MAINTENANCE_OPERATOR` | Ops-specific access; limited household assistant access | Service technicians, trusted operators |

## Permission matrix

| Permission | FOUNDER_ADMIN | ADULT_MEMBER | CHILD_GUEST | MAINTENANCE_OPERATOR |
|-----------|:-------------:|:------------:|:-----------:|:-------------------:|
| PERSONAL memory (own) | ✓ | ✓ | ✓ (limited) | ✓ |
| HOUSEHOLD_SHARED memory | ✓ | ✓ | ✗ | ✗ |
| SITE_SYSTEM memory | ✓ | read-only | ✗ | ✓ |
| T0 Inform | ✓ | ✓ | ✓ | ✓ |
| T1 Suggest | ✓ | ✓ | ✓ | ✓ |
| T2 Draft | ✓ | ✓ | ✗ | ✓ (ops only) |
| T3 Execute (personal) | ✓ | ✓ | ✗ | ✓ (ops-relevant only) |
| T3 Execute (household) | ✓ | ✓ | ✗ | ✗ |
| T3 Execute (site read-only) | ✓ | ✓ | ✗ | ✓ |
| T4 Execute (site control) | ✓ | ✗ | ✗ | ✓ (with approval) |
| T5 Never | ✗ | ✗ | ✗ | ✗ |
| Job approval (LOW) | ✓ | ✗ | ✗ | ✓ |
| Job approval (HIGH/CRITICAL) | ✓ | ✗ | ✗ | ✗ |
| Emergency mode trigger | ✓ | ✗ | ✗ | ✗ |
| Emergency mode acknowledge | ✓ | ✗ | ✗ | ✗ |
| PERSONAL mode (own) | ✓ | ✓ | ✓ | ✓ |
| FAMILY mode | ✓ | ✓ | ✓ (limited) | ✗ |
| WORK mode | ✓ | ✗ | ✗ | ✗ |
| SITE mode | ✓ | ✗ | ✗ | ✓ |
| EMERGENCY mode | ✓ | ✗ | ✗ | ✗ |

## Role lifecycle

1. **Role creation**: FOUNDER_ADMIN creates a household member account in identity-service.
2. **Role assignment**: Role is assigned at account creation; can be changed by FOUNDER_ADMIN.
3. **Role removal**: FOUNDER_ADMIN can revoke access; sessions are invalidated immediately.
4. **Guest access**: CHILD_GUEST role can be temporary (time-bounded) or permanent.
5. **Maintenance access**: MAINTENANCE_OPERATOR role can be time-bounded for service visits.

## Child safety design

CHILD_GUEST users:
- Can use voice and family-web in family mode with age-appropriate filters
- Cannot access personal memory of other users
- Cannot trigger any site control or household routine modification
- Response content is filtered by age-appropriateness rules in `packages/persona/`
- Cannot switch modes or view adult conversation history

## Permission enforcement

All permission checks are enforced in:
1. **identity-service**: role validation on auth tokens
2. **context-router**: role → mode mapping, max_tool_tier calculation
3. **memory-service**: scope access validation per request
4. **model-router**: tool tier enforcement via capability-policy
5. **orchestrator**: approval mode enforcement per risk_class and requestor role

No permission relies solely on model behavior. All are code-enforced.
