# ADR-014: Assistant actions are policy-tiered into personal, household, and site-control scopes

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

The assistant must handle a wide range of requests: personal reminders (low stakes), household calendar (medium stakes), site control (high stakes). Without a formal tier model, the assistant's behavior on high-stakes requests depends on prompt engineering alone — which is insufficient for a safety-critical system.

## Decision

All assistant actions are assigned a trust tier (T0–T5; see assistant-trust-tiers.md). Trust tiers are enforced in code, not just in prompts.

### Enforcement chain

1. **Tool registration**: Every tool specifies its `capability_tier` at registration time.
2. **context-router**: Produces `max_tool_tier` in context envelope based on user role and operating mode.
3. **model-router**: Filters available tools to those at or below `max_tool_tier` before passing them to the model.
4. **assistant-tools**: T4 tools (site control) always call control-api → orchestrator, which performs risk class check and approval requirement.
5. **T5 actions**: Not registered in the tool registry. Cannot be called regardless of model output.

### Why this matters

An LLM can generate a tool call for any tool name. If T5 tools exist in the registry, a jailbreak or adversarial prompt could trigger them. By not registering T5 tools, there is nothing to call.

Similarly, if a user is in FAMILY mode (max_tool_tier=T3), model-router will not offer T4 tools to the model even if the model requests them.

## Consequences

- Trust tiers provide a code-enforced safety boundary that prompt engineering cannot bypass.
- Adding a new tool always requires explicit tier assignment.
- Tier changes require a code change (PR + CI) not a configuration edit.
- This is intentional: tier assignments should be deliberate, not runtime-adjustable.
