## Summary

_What does this PR do? One paragraph, no marketing._

## Type of change

- [ ] Bug fix
- [ ] New feature / capability
- [ ] Refactor (no functional change)
- [ ] Documentation
- [ ] Infrastructure / CI
- [ ] Policy / safety change

---

## Contract changes

- [ ] No contract changes
- [ ] Changes to `packages/runtime-contracts` types
- [ ] Changes to `packages/contracts` types
- [ ] Changes to MCP tool registry (new/modified/removed tools)
- [ ] Changes to OpenFGA authorization model

_If contract changes: describe the change and confirm downstream services are updated._

---

## Policy impact

- [ ] No policy impact
- [ ] Changes attention thresholds or suppression parameters
- [ ] Changes confidence thresholds
- [ ] Changes memory decay or loop lifecycle parameters
- [ ] Changes trust tier assignments

_If policy impact: has a `PolicyImpactReport` been filed? Has replay been run?_

See [`docs/delivery/policy-publish-gate.md`](docs/delivery/policy-publish-gate.md).

---

## Safety implications

- [ ] No safety implications
- [ ] Modifies or adds safety invariants
- [ ] Affects CRK step 4 (safety check)
- [ ] Changes orchestrator dispatch logic
- [ ] Affects robot control path

_If safety implications: describe the impact and confirm invariants I-01 through I-09 are still enforced._

---

## Requires replay?

- [ ] No replay required
- [ ] Replay required — `PolicyImpactReport` filed: `pir-_____`
- [ ] Replay required — replay complete, divergence rate: `____%`

---

## New MCP tools (if any)

For each new tool, confirm all five admission criteria are met:

| Tool name | Primary mode | Trust tier | Failure mode | Eval fixture | Audit payload |
|-----------|-------------|-----------|-------------|-------------|--------------|
| | | | | | |

See [`docs/architecture/tool-admission-policy.md`](docs/architecture/tool-admission-policy.md).

---

## Testing

- [ ] Unit tests pass (`task test:all`)
- [ ] Calibration tests pass (`task test:calibration`)
- [ ] Rubric passes (`python3 scripts/perfection_rubric.py`)
- [ ] Relevant SITL scenarios pass (if robotics/site change)
- [ ] New eval fixtures added (if new behavior)

---

## Documentation

- [ ] README updated (if service/package changed)
- [ ] Architecture doc updated (if architectural change)
- [ ] ADR added (if new architectural decision)
- [ ] Docs index regenerated (`python3 scripts/generate_docs_index.py`)
