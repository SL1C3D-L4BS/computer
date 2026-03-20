# Change Control

Governs how changes to Computer are proposed, reviewed, tested, and merged. Different change types have different control requirements.

## Change types

| Type | Examples | Control requirement |
|------|---------|-------------------|
| `patch` | Bug fix, typo, test addition | PR review + CI pass |
| `feature` | New service, new endpoint, new tool | PR review + CI pass + integration test |
| `contract` | Schema change, API change, event schema change | PR review + contract-gate + codegen re-run + dependent service update |
| `policy` | Risk class change, approval mode change, tool tier change | PR review + safety-gate + operator sign-off |
| `architecture` | New ADR, service boundary change, new runtime dependency | ADR required + PR review + CI pass |
| `compatibility` | Version pin change, runtime upgrade | Compatibility sprint (see compatibility-policy.md) + full lane tests |
| `robotics` | ROS2 changes, PX4 changes, SITL changes | Robotics gate + SITL pass + operator sign-off |
| `release` | Production deployment | Release gate + backup verified + rollback plan documented |

## Fitness function enforcement

Every PR is checked against applicable fitness functions (see `architecture-fitness.md`). Required CI status checks:

| Status check | Required for |
|-------------|-------------|
| `contract-gate` | All PRs touching `packages/contracts/`, `packages/assistant-contracts/`, any `apps/*/routes.py` |
| `safety-gate` | All PRs touching `apps/model-router/`, `apps/orchestrator/`, `packages/policy/` |
| `audit-gate` | All PRs touching orchestrator state machine or command dispatch |
| `robotics-gate` | All PRs touching `robotics/`, `services/rover-control/`, `services/drone-control/` |
| `release-gate` | Release tags only |

## ADR requirement

An ADR is required for:
- Any change to service boundaries (service-responsibility-matrix.md)
- Any new runtime dependency (new language, new database, new message broker)
- Any change to the orchestrator state machine that adds or removes states
- Any change to the policy domain model
- Any removal of a fitness function

An ADR is not required for:
- Feature additions within existing service boundaries
- Bug fixes
- Version updates (handled by compatibility policy)

## Schema change process

1. Update schema file in `packages/contracts/` or `packages/assistant-contracts/`.
2. Run `pnpm contracts:generate` to regenerate Pydantic models, TypeScript types, SDK clients.
3. Update all affected services (tests will catch missing updates).
4. PR must include generated code changes alongside schema change.
5. contract-gate validates that generated code matches schema.

Schema changes that remove fields or change field types are **breaking changes** and require a migration plan and API versioning strategy documented in the PR.

## Production deployment process

1. Create release branch from main.
2. Run full CI (all gates).
3. Create release tag with class prefix (e.g., `site-stable/orchestrator/v1.2.0`).
4. Release workflow verifies: rollback metadata present, backup verified, release notes written.
5. Deploy to production via Ansible or compose update.
6. Verify health at each tier.
7. Operator confirms system operational.

## Rollback triggers

Automatic rollback triggers (implemented in deploy pipeline):
- Tier health check failure after deploy
- Error rate spike (> 5% 5xx within 5 minutes of deploy)

Manual rollback: operator runs rollback procedure from `docs/runbooks/rollback-procedures.md`.
