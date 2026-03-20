# ADR-001: computer is a monorepo, not a monolith

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Computer has multiple runtimes (TypeScript frontend, Python backend, ROS2 robotics, firmware), multiple deployment targets (cloud-adjacent services, edge nodes, MCUs), and tight cross-service contracts. The question is whether to use one repo or multiple repos.

## Decision

Use a single monorepo named `computer` for all components.

## Reasons

1. **Shared contracts**: Job schemas, event schemas, and command schemas must be consistent across all services. A monorepo enforces this via `packages/contracts/` as the single source of truth.
2. **Atomic changes**: A change to the job schema requires updating the orchestrator, control-api, and all SDK consumers simultaneously. Monorepo enables one PR to cover all affected code.
3. **Shared tooling**: `versions.json`, `Taskfile.yml`, CI pipeline, Docker Compose stacks, and Ansible playbooks benefit from being co-located.
4. **Easier cross-service testing**: Integration tests can import from multiple services without complex versioning.
5. **Not a monolith**: Services have hard boundaries enforced by contract tests and CI. The monorepo is a code organization strategy, not an architecture strategy.

## Consequences

- All services are in one repo; PR review must be aware of blast radius.
- Turborepo is used to enable parallel builds and affected-package CI filtering.
- Robotics code (`robotics/`) is co-located but has its own CI lane to avoid contaminating web/backend CI with ROS2 toolchain dependencies.
- `uv` manages Python workspaces; `pnpm` manages TypeScript workspaces; both are integrated via Taskfile.

## Rejected alternatives

- **Separate repos per service**: Cross-service contracts become difficult to manage; schema versioning complexity; no atomic changes across service boundaries.
- **Monolith**: Violates hard service boundaries and deployment independence.
