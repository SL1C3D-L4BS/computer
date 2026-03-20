# Contributing

> Contribution guidelines for the Computer monorepo. Read before opening a PR.

---

## Core principles

1. **Safety over velocity.** If a change touches safety invariants, actuation paths, or policy evaluation, it moves slowly and deliberately.
2. **Contracts first.** Change the type before changing the behavior.
3. **No silent decisions.** Every behavioral change must have an eval fixture, an audit payload, and a trace.
4. **No tool sprawl.** Every new MCP tool requires all five admission criteria. No exceptions.

---

## Before you start

- Search existing issues and PRs before opening a new one.
- For architectural changes, open an issue first and discuss before writing code.
- For new workflow classes, an ADR is required.

---

## Development setup

```bash
git clone git@github.com:SL1C3D-L4BS/computer.git
cd computer
./bootstrap.sh
task test:all
python3 scripts/perfection_rubric.py
```

All checks must pass before any PR is opened.

---

## Contribution types

### Bug fixes

- File a bug report issue first (use the bug report template).
- Include a `computer trace` output if the bug involves a CRK execution.
- Fixes to safety-critical paths require two reviewers.

### New features

- Open an issue describing the feature and its scope before coding.
- Features that add new services require a design doc and ADR.
- Features that add new MCP tools require the tool proposal issue template.

### Documentation

- Follow [`docs/standards/documentation-style-guide.md`](docs/standards/documentation-style-guide.md).
- Use the README template for new service/package READMEs.
- Regenerate docs index after any docs change: `python3 scripts/generate_docs_index.py`.

### Policy changes

Policy changes (attention thresholds, confidence thresholds, decay rates) require:

1. `PolicyImpactReport` filed before replay
2. Replay against ≥N historical traces
3. Divergence rate within threshold
4. Passkey re-auth at publish time

See [`docs/delivery/policy-publish-gate.md`](docs/delivery/policy-publish-gate.md).

---

## PR checklist

Use the PR template. At minimum:

- [ ] Tests pass (`task test:all`)
- [ ] Rubric passes (`python3 scripts/perfection_rubric.py`)
- [ ] README updated if service/package changed
- [ ] Contract changes documented
- [ ] No new tools without admission criteria

---

## Commit style

```
type(scope): short description

Longer explanation if needed. Focus on why, not what.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `infra`, `policy`, `safety`

---

## Code review

- Minimum one reviewer for routine changes.
- Two reviewers required for: safety invariant changes, policy changes, auth changes, new workflow classes.
- Reviewers check: behavioral correctness, contract integrity, invariant preservation, test coverage.
