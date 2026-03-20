# Tool Admission Policy

**Status:** Active | **Enforced by:** `perfection_rubric.py` `v4_operational` category  
**Owner:** MCP gateway maintainer  
**Version:** 1.0.0

---

## Purpose

Every tool registered in `mcp-gateway` is a trust surface. A tool that lacks a clear failure mode, missing authorization context, or no eval coverage is a security and reliability liability. This policy prevents registry entropy by requiring every tool to satisfy five admission criteria before merging.

This applies **retroactively to all existing tools** and is enforced by the rubric.

---

## Five Admission Criteria

Every `ToolDescriptor` entry in `registry.py` must satisfy all five criteria:

| Criterion             | Requirement                                                                      |
| --------------------- | -------------------------------------------------------------------------------- |
| **Primary mode**      | One named mode: `PERSONAL` / `FAMILY` / `WORK` / `SITE` / `EMERGENCY`          |
| **Trust tier**        | One of T0–T4 with written justification in the docstring or inline comment      |
| **Explicit failure mode** | What the tool returns when it cannot fulfill the request (error type + fallback behavior) |
| **Eval fixture**      | One entry in `packages/eval-fixtures/eval_fixtures/` covering the tool's primary path |
| **Audit payload example** | A sample `DecisionRationale` JSON block in the tool's docstring                |

---

## Trust Tiers

| Tier | Scope                                                   | Examples                                          |
| ---- | ------------------------------------------------------- | ------------------------------------------------- |
| T0   | Read-only, no state change, no PII                      | `site.read_snapshot`, `sensors.confidence_report` |
| T1   | Household-shared data, low-consequence writes           | `shopping.plan_week`, `chores.balance_load`       |
| T2   | Work context, founder mode, reversible decisions        | `briefing.daily`, `decisions.diff`                |
| T3   | Site operations, non-reversible or high-latency effects | `energy.peak_window_plan`, `jobs.pending_risk`    |
| T4   | Emergency, safety-critical, requires operator_approved  | Emergency actuation, safety overrides             |

---

## Three Hard Rules

1. **No tool merge without all five criteria present** — a PR that adds a tool without satisfying the checklist is rejected at rubric gate.
2. **Every tool must have one named owner** — ownership is required for deprecation decisions and drift investigation.
3. **Failure modes must be explicit, not implied** — "returns None" or "raises Exception" is not sufficient. The tool must document what the caller should do.

---

## Admission Checklist (for reviewers)

Before approving a new tool registration:

- [ ] `primary_mode` field is set to one of the five valid modes
- [ ] `trust_tier` is set with justification
- [ ] `failure_mode` documents the error return type and fallback
- [ ] An eval fixture exists and covers the primary invocation path
- [ ] Docstring includes a sample `DecisionRationale` JSON block
- [ ] `tool audit` passes with no admission violations for the new entry

---

## Enforcement

The `v4_operational` rubric category checks:
- `tool-admission-policy.md` exists
- All registered tools have `primary_mode`, `trust_tier`, `failure_mode`, `eval_fixture`, `audit_payload`
- `computer tool audit` exits 0

See also: [`tool-lifecycle-policy.md`](tool-lifecycle-policy.md)
