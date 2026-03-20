# Family Assistant Specification

Defines the Computer household assistant as a product — its capabilities, interaction model, and what distinguishes it from the ops assistant.

## Product definition

The family assistant is a **persistent, memory-aware household intelligence** for daily life coordination. It is:
- Voice-first but equally real on family-web
- Available to all household members at their appropriate role level
- Not an ops tool — physical site control requires explicit mode switch and approval

The family assistant is a first-class product, not a thin wrapper over ops-web.

## Core household capabilities

### Shared calendar and scheduling
- Add, update, and read household calendar events
- Conflict detection and suggestions
- Integration with individual personal calendars (with permission)
- Reminders for upcoming events

### Grocery and shopping
- Shared grocery list (any adult member can add/remove)
- Low-stock suggestions from meal plans
- Shopping history for recurring items
- Optional: order integration (T2 draft + T3 confirm)

### Household chores and tasks
- Shared chore list with assignees and due dates
- Completion tracking
- Routine-linked tasks (e.g., Monday cleaning checklist)
- Nudge reminders for overdue tasks

### Meal planning
- Weekly meal plan with household preferences
- Grocery list auto-generation from meal plan
- Dietary restriction awareness (stored in household memory)

### Household notes and information
- Shared notes visible to all household members
- Important household information (WiFi passwords, maintenance contacts, appliance manuals)
- Emergency contacts and procedures

### Household routines
- Morning routine, bedtime routine, etc.
- Triggered by time, voice, or sensor (presence, sunrise/sunset)
- Routine steps can include T3 home actions (lights, thermostat)
- Routines are pre-registered and approved before being enabled

## What the family assistant does NOT do

- Direct site control (irrigation, greenhouse, energy) — routes to ops plane with T4 approval
- Access personal private memory of other household members
- Perform external purchases without explicit confirmation
- Share household information with external services without authorization
- Operate in SITE mode (family members use ops-web for that)

## Household interaction patterns

### Morning briefing (example)
```
User: "Good morning, Computer"
Computer: "Good morning. Today's schedule: school pickup at 3pm, dinner reservation at 7pm.
           It's currently 38°F outside and frost is expected tonight.
           Greenhouse zone A is running normally.
           Your grocery list has 8 items — milk and eggs are flagged low."
```

Morning briefings combine HOUSEHOLD_SHARED data (calendar, groceries) with SITE_OPS read-only (greenhouse status, weather). No T4 actions are proposed in a morning briefing.

### Household coordination (example)
```
User: "Add salmon to the grocery list and remind Sarah to pick up bread"
Computer: "Added salmon to the grocery list. I'll remind Sarah to pick up bread."
```

Both are T3 actions: shopping-tool write + reminder-tool (for another household member, with permission). The system knows Sarah's identity from identity-service and can send a cross-user reminder within household-shared scope.

## Family-safe design principles

1. **No cross-user private memory access.** Even FOUNDER_ADMIN cannot read another member's PERSONAL mode memory through the family assistant.
2. **Age-appropriate responses.** context-router knows when a CHILD_GUEST is the active user and filters responses appropriately.
3. **No in-room broadcasting of private information.** Voice in FAMILY mode does not reveal individual members' private reminders, notes, or calendar items.
4. **Explicit sharing only.** Information shared with the household is explicitly added to HOUSEHOLD_SHARED scope; it does not automatically migrate from PERSONAL.

## Relationship to ops assistant

| Family assistant | Ops assistant (Site mode) |
|-----------------|--------------------------|
| Household members | FOUNDER_ADMIN or MAINTENANCE_OPERATOR |
| Daily life coordination | Site monitoring and control |
| family-web, voice | ops-web, voice (SITE mode) |
| T3 max (except site read-only) | T4 with approval |
| HOUSEHOLD_SHARED + PERSONAL memory | SITE/SYSTEM memory |

They share the same assistant-api, context-router, and model-router infrastructure. The mode and role determine which capabilities are active.
