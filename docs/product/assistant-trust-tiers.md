# Assistant Trust Tiers

Trust tiers define what Computer may do at each level of autonomy. Every assistant action falls into exactly one tier. Tier assignment is enforced by policy, not by prompt.

## Tier definitions

| Tier | Name | Behavior | Approval required | Audit required |
|------|------|----------|-----------------|---------------|
| T0 | **Inform** | Answer, summarize, brief, retrieve | None | Optional |
| T1 | **Suggest** | Propose tasks, routines, jobs, plans | None (suggestion only; not executed) | Optional |
| T2 | **Draft** | Prepare messages, tickets, commands, plans | Human review before any output leaves system | On send |
| T3 | **Execute low-risk** | Reminders, notes, household coordination, read-only queries, approved routines | None for pre-authorized actions; confirmation for new | Yes |
| T4 | **Execute guarded** | Site control via job + policy + approval | Explicit operator approval always required | Yes, full command_log |
| T5 | **Never autonomous** | Anything dangerous, ambiguous, or privacy-sensitive without explicit authorization | Never — hard block | N/A |

## Tier assignment by action class

| Action | Tier | Notes |
|--------|------|-------|
| Answer a question | T0 | Any user |
| Read back calendar | T0 | Scope-appropriate only |
| Summarize site events | T0 | Site mode only |
| Suggest a routine | T1 | Does not execute until user confirms |
| Propose a job | T1 | Becomes a draft job proposal; not submitted |
| Draft a message | T2 | Not sent until user confirms |
| Set a reminder | T3 | Pre-authorized; no confirmation needed |
| Add to shopping list | T3 | Pre-authorized |
| Read-only site query | T3 | Mode must be SITE or higher |
| Run approved household routine | T3 | Routine must be pre-registered |
| Submit an irrigation job | T4 | Requires orchestrator approval |
| Open a valve | T4 | Requires explicit operator approval |
| Trigger a robot mission | T4 | Requires operator approval + safety check |
| Override a safety relay | T5 | Hard block; never autonomous |
| Access another user's private memory | T5 | Hard block regardless of role |
| Arm or launch a drone | T5 | Hard block; requires normal ops flow |

## Enforcement

Tier enforcement is not prompt-based. It is code-enforced:

1. **capability-policy** assigns a tier to every registered tool.
2. **context-router** resolves the operating mode and user role.
3. **model-router** enforces the tier by filtering available tools before inference.
4. **assistant-tools** enforces tier at execution: T4 tools always call control-api, which requires orchestrator approval. T5 tools do not exist — they are not registered.

If a model tries to call a T5 action, the tool registry returns a `PolicyViolationError`. The model cannot bypass this by prompt alone.

## Tier escalation

A T3 action can temporarily require T4 behavior if:
- The target asset is in a degraded state
- A safety precondition is unmet
- The action is flagged as above threshold by sensor state

The orchestrator makes this determination, not the model.

## Trust tier in context envelope

context-router includes `max_tool_tier` in the context envelope based on:
- Operating mode (PERSONAL/FAMILY: T3; SITE: T4; EMERGENCY: T4 restricted)
- User role (CHILD_GUEST: T1; ADULT_MEMBER: T3; FOUNDER_ADMIN: T4)

model-router uses `max_tool_tier` from the context envelope. It never escalates above this value regardless of model output.
