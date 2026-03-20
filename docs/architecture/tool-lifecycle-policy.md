# Tool Lifecycle Policy

**Status:** Active | **Enforced by:** `perfection_rubric.py` `v4_operational` category  
**Owner:** MCP gateway maintainer  
**Version:** 1.0.0

---

## Purpose

Admission is only the first gate. Tools accumulate. Without a managed lifecycle, the registry becomes a graveyard of stale, overlapping, or ownership-free tools. This policy defines the four stages every tool passes through and the criteria that govern each transition.

`computer tool prune` surfaces all tools eligible for deprecation. `computer tool audit` surfaces admission violations.

---

## Lifecycle Stages

| Stage        | Description                                                                  | Entry condition                                 |
| ------------ | ---------------------------------------------------------------------------- | ----------------------------------------------- |
| **Proposed** | Admission checklist complete; tool not yet registered; awaiting review       | PR submitted with full admission criteria        |
| **Active**   | Registered in `registry.py`; eval fixture passing; ownership assigned        | Admission criteria verified + rubric passes      |
| **Deprecated** | Flagged for removal; `deprecated_at` timestamp set; still callable but warns | Meets any deprecation criterion (see below)     |
| **Removed**  | Unregistered from `registry.py`; removal entry in registry changelog         | 30-day deprecation window elapsed + owner sign-off |

---

## Deprecation Criteria

A tool becomes eligible for deprecation if **any** of the following are true:

1. **Unused for 30+ days** — no invocation events in audit log for the tool's `name`
2. **Superseded by another tool** — a newer tool covers the same primary path with a tighter contract
3. **Ownership unclear** — no named owner and no response within 7 days of ownership inquiry
4. **Eval fixture failing persistently** — fixture fails for 3+ consecutive rubric runs with no open fix
5. **Admission criteria retroactively violated** — e.g., primary mode removed without update

`computer tool prune` surfaces all candidates. Deprecation must be approved by the tool's owner or the MCP gateway maintainer.

---

## Deprecation Procedure

1. Set `deprecated_at` in the `ToolDescriptor` entry (ISO timestamp)
2. Add deprecation reason to the docstring
3. Callsite warning emitted on invocation for the deprecation window (30 days)
4. After 30 days: unregister from `registry.py`, add changelog entry
5. Run `computer tool audit` to confirm removal does not break admission check counts

---

## Version Bumping

Every change to a tool's behavior, schema, or auth tier requires a version bump in the `ToolDescriptor`:
- Patch: docstring/metadata only
- Minor: new optional parameters, expanded failure modes
- Major: breaking input/output schema change, tier change, mode change

Workers serving the tool must handle at minimum the current and previous major version during rollover.

---

## Registry Changelog

Maintain a changelog entry for every Removed tool in `packages/mcp-gateway/CHANGELOG.md`:

```
## [date] Removed: <tool_name>
- Reason: <deprecation criterion>
- Deprecated at: <deprecated_at date>
- Owner sign-off: <owner>
- Replacement: <new tool name, if any>
```

---

## Tool Growth Quota

Per the V4 plan: **no additional MCP tools beyond the V4.1 set of 32** without an ADR. New tool additions must go through the admission checklist and be reviewed against the quota. If a new tool is added, a deprecated tool must be removed within the same release cycle.

See also: [`tool-admission-policy.md`](tool-admission-policy.md)
