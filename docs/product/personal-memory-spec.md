# Personal Memory Specification

Defines the three memory scopes, their contents, access rules, and implementation boundaries.

## Three memory scopes (do not mix)

| Scope | Contents | Who can read | Who can write | Retention |
|-------|---------|-------------|--------------|-----------|
| **PERSONAL** | Individual preferences, reminders, notes, routines, work context | That individual only | That individual only | Indefinite; user-deletable |
| **HOUSEHOLD_SHARED** | Groceries, calendars, chores, home routines, common preferences, emergency contacts | All non-CHILD_GUEST household members | ADULT_MEMBER and above | Indefinite; any authorized member can delete |
| **SITE_SYSTEM** | Jobs, assets, incidents, maintenance, telemetry summaries, site config | FOUNDER_ADMIN, MAINTENANCE_OPERATOR | Orchestrator, control services (not user-written) | Per retention policy in backup-retention-dr.md |

## Scope enforcement

Scope enforcement is code-enforced in memory-service, not prompt-enforced.

Every memory read and write call includes a `scope` parameter:
```python
memory_service.read(
    user_id="user_001",
    scope=MemoryScope.PERSONAL,
    query="reminders for today"
)
```

memory-service validates that the requesting user has access to the requested scope. If validation fails, it returns a `ScopeViolationError`, never a partial result.

context-router includes `eligible_memory_scopes: list[MemoryScope]` in the context envelope. model-router passes only eligible scopes to memory-service.

## Memory types within scopes

### PERSONAL memory types

| Type | Example | Notes |
|------|---------|-------|
| Reminders | "Call dentist on Friday" | Time-indexed; expires after trigger |
| Notes | "Gift ideas for spouse" | Free-form; user-tagged |
| Preferences | "Prefers short responses in morning" | Structured; affects response style |
| Routines | "Morning routine: 7am, coffee, news briefing" | Triggers and steps |
| Work context | "Current project: phase B implementation" | FOUNDER_ADMIN only; WORK scope |
| Task list | "Deploy ops-web by EOW" | Personal tasks |

### HOUSEHOLD_SHARED memory types

| Type | Example |
|------|---------|
| Calendar events | "School pickup 3pm Tuesday" |
| Shopping list | "Milk, eggs, salmon" |
| Chore assignments | "Sarah: vacuum living room by Sunday" |
| Household preferences | "No pork in meal plans" |
| Home routines | "Good night: doors locked, heating lowered" |
| Emergency contacts | "Plumber: 555-0123" |

### SITE_SYSTEM memory types (system-managed, not user-written)

| Type | Written by |
|------|-----------|
| Job records | orchestrator |
| Asset telemetry summaries | event-ingest |
| Incident records | frigate-adapter, osint-ingest |
| Maintenance notes | orchestrator (operator-tagged jobs) |
| Site config snapshots | digital-twin |

## Retrieval model

memory-service uses vector embeddings for semantic retrieval within scope:

1. User query arrives at model-router with context envelope including eligible scopes.
2. model-router calls `memory_service.retrieve(query, scopes, user_id, limit)`.
3. memory-service embeds the query and searches within the eligible scopes only.
4. Returns ranked results with source scope labeled.
5. model-router includes results in model context window.

Embeddings are generated locally (no cloud embedding API). Embedding model stored in `services/memory-service/`.

## Privacy rules

1. PERSONAL scope data is never included in HOUSEHOLD_SHARED or SITE_SYSTEM queries.
2. HOUSEHOLD_SHARED data is visible in shared contexts but not in another user's PERSONAL context.
3. Deletion is immediate: memory-service deletes the record and its embedding; no soft-delete for PERSONAL scope.
4. Memory export: any household member can request a full export of their PERSONAL memory in JSON format.
5. Memory is not shared with external services unless explicitly authorized per tool call.

## Retention policy

| Scope | Default retention | User override |
|-------|-----------------|--------------|
| PERSONAL | Indefinite | User can delete any or all records |
| HOUSEHOLD_SHARED | Indefinite | Any authorized member can delete shared records |
| SITE_SYSTEM (events) | 90 days (configurable) | Operator can extend or reduce |
| SITE_SYSTEM (jobs) | 365 days (configurable) | Operator can extend |
| SITE_SYSTEM (telemetry) | 30 days (configurable) | Operator can extend |

Retention policy is configured in `packages/config/site.yaml`.
