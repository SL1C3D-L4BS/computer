# Assistant Tooling Specification

Defines the tool registry, tool registration contract, and all tools available to the assistant.

## Tool registration contract

Every tool registered in the assistant tool registry must specify:

```python
class AssistantTool:
    name: str                    # Unique tool name (snake_case)
    description: str             # Human and model-readable description
    capability_tier: ToolTier    # T0–T4 (T5 never registered)
    memory_scopes: list[MemoryScope]  # Which memory scopes this tool reads/writes
    allowed_roles: list[Role]    # Which household roles may use this tool
    allowed_modes: list[Mode]    # Which operating modes permit this tool
    requires_confirmation: bool  # True for T3 actions that modify state
    is_site_control: bool        # True if routes through control-api/orchestrator
    schema: dict                 # JSON Schema for input/output
```

model-router enforces tier, role, and mode checks before calling any tool. If any check fails, the tool is not called and the model receives a `ToolNotAvailable` response.

## Tool registry

### Personal productivity tools

| Tool | Tier | Notes |
|------|------|-------|
| `reminder_create` | T3 | Creates reminder in PERSONAL scope |
| `reminder_list` | T0 | Lists upcoming reminders |
| `task_create` | T3 | Creates task in PERSONAL scope |
| `task_list` | T0 | Lists tasks |
| `task_complete` | T3 | Marks task complete |
| `notes_create` | T3 | Creates note in PERSONAL scope |
| `notes_read` | T0 | Reads notes from PERSONAL scope |
| `calendar_read_personal` | T0 | Reads personal calendar |
| `calendar_write_personal` | T3 | Writes personal calendar event |
| `work_context_read` | T0 | Reads WORK scope memory |
| `work_context_write` | T3 | Writes WORK scope memory |

### Household coordination tools

| Tool | Tier | Notes |
|------|------|-------|
| `shopping_list_add` | T3 | Adds item to HOUSEHOLD_SHARED shopping list |
| `shopping_list_read` | T0 | Reads shopping list |
| `shopping_list_remove` | T3 | Removes item |
| `calendar_read_household` | T0 | Reads household calendar |
| `calendar_write_household` | T3 | Writes household calendar event |
| `chores_create` | T3 | Creates chore assignment |
| `chores_list` | T0 | Lists chores |
| `chores_complete` | T3 | Marks chore complete |
| `household_notes_read` | T0 | Reads household notes |
| `household_notes_write` | T3 | Writes household note |
| `reminder_create_household` | T3 | Creates reminder for another household member (requires role) |
| `meal_plan_read` | T0 | Reads meal plan |
| `meal_plan_write` | T3 | Updates meal plan |

### Site operations tools (Site mode only)

| Tool | Tier | Notes |
|------|------|-------|
| `site_status_query` | T0 | Read-only site health summary |
| `asset_query` | T0 | Query asset state from digital-twin |
| `job_list` | T0 | List recent jobs |
| `job_detail` | T0 | Get job detail |
| `job_propose` | T4 | Propose a job to orchestrator (requires approval) |
| `job_approve` | T4 | Approve a pending job (FOUNDER_ADMIN only) |
| `incident_list` | T0 | List security/sensor incidents |
| `incident_detail` | T0 | Get incident detail |
| `ops_briefing` | T0 | Generate ops summary |

### Information and research tools

| Tool | Tier | Notes |
|------|------|-------|
| `web_search` | T0 | External web search |
| `doc_search` | T0 | Search internal docs (runbooks, ADRs) |
| `memory_retrieve` | T0 | Semantic search within eligible scopes |
| `weather_query` | T0 | Local weather (via API or sensor) |

### Notification and communication tools

| Tool | Tier | Notes |
|------|------|-------|
| `notification_send` | T3 | Sends in-app notification to household member |
| `message_draft` | T2 | Drafts message; requires confirmation to send |
| `message_send` | T3 | Sends message (requires prior draft confirmation) |

### Emergency tools (Emergency mode only)

| Tool | Tier | Allowed roles |
|------|------|--------------|
| `emergency_mode_trigger` | T4 | FOUNDER_ADMIN only |
| `emergency_valve_close` | T4 | FOUNDER_ADMIN only |
| `emergency_ventilation` | T4 | FOUNDER_ADMIN only |
| `emergency_rover_stop` | T4 | FOUNDER_ADMIN only |
| `emergency_drone_land` | T4 | FOUNDER_ADMIN only |

## Tool execution flow

```
model-router receives tool call request
    │
    ▼
capability-policy.check_tier(tool, context_envelope)
    │
    ├── FAIL → ToolNotAvailable (model receives graceful error)
    │
    └── PASS
        │
        ▼
    assistant_tools.execute(tool, args)
        │
        ├── Non-site tools → direct execution → memory-service, calendar API, etc.
        │
        └── Site tools (is_site_control=True)
            │
            ▼
        control-api (HTTP POST) → orchestrator → approval flow
```

## Tool versioning

Tool schemas are versioned in `packages/assistant-contracts/tools/`. Breaking tool schema changes (removed fields, changed types) require:
1. New tool version (`reminder_create_v2`)
2. Deprecation period for old version
3. Migration in assistant-tools service

Adding optional fields to a tool schema is non-breaking.
