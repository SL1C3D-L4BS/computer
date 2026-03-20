---
name: New MCP tool proposal
about: Propose adding a new tool to the mcp-gateway registry
labels: tool-proposal
---

## Tool name

`domain.action_name`

## Justification

_Why does this tool need to exist? What problem does it solve that existing tools cannot?_

## Admission criteria

All five criteria must be met before this tool can be registered:

| Criterion | Value |
|-----------|-------|
| Primary mode | PERSONAL / FAMILY / WORK / SITE / EMERGENCY |
| Trust tier | T0 / T1 / T2 / T3 / T4 |
| Failure mode | What the tool returns if it cannot fulfill the request |
| Eval fixture | Name of the fixture that will be added to `eval-fixtures` |
| Audit payload example | (paste sample `DecisionRationale` JSON below) |

## Audit payload example

```json
{
  "tool": "domain.action_name",
  "decision": "invoke",
  "confidence": 0.90,
  "trust_tier": "T2",
  "mode": "WORK",
  "rationale": "..."
}
```

## Tool registry entry draft

```python
ToolDescriptor(
    name="domain.action_name",
    title="Human-readable title",
    description="What this tool does",
    trust_tier="T2",
    domain="work",
    surfaces=["cli", "assistant"],
)
```

## Does this replace an existing tool?

- [ ] No
- [ ] Yes — replaces: `tool.name` (deprecation plan: )

See [`docs/architecture/tool-admission-policy.md`](../../docs/architecture/tool-admission-policy.md).
