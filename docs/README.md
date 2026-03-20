# Documentation Index

> Auto-generated index of all documentation in the Computer monorepo. Run `python3 scripts/generate_docs_index.py` to refresh.

---

## Architecture

| Document | Summary |
|----------|---------|
| [Authorization Evolution](docs/architecture/authorization-evolution.md) |  |
| [Cross-Domain Priority Model](docs/architecture/cross-domain-priority-model.md) |  |
| [Durable Workflow Strategy](docs/architecture/durable-workflow-strategy.md) |  |
| [Kernel Authority Model](docs/architecture/kernel-authority-model.md) |  |
| [Local-First Sync Strategy — family-web](docs/architecture/local-first-sync-strategy.md) |  |
| [Missing Runtime Planes](docs/architecture/missing-runtime-planes.md) |  |
| [Objective Functions](docs/architecture/objective-functions.md) | In EMERGENCY mode, `timeliness` dominates. All soft objectives that would delay … |
| [Passkey Authentication Strategy — family-web](docs/architecture/passkey-auth-strategy.md) |  |
| [Policy Domain Model](docs/architecture/policy-domain-model.md) |  |
| [ReBAC Authorization Evolution Strategy](docs/architecture/rebac-auth-evolution.md) |  |
| [Runtime Glue and System Cohesion](docs/architecture/runtime-glue-and-cohesion.md) |  |
| [Computer Runtime Kernel (CRK)](docs/architecture/runtime-kernel.md) | Every request must have **one owner at every step**, one durable context, one au… |
| [Service Responsibility Matrix](docs/architecture/service-responsibility-matrix.md) |  |
| [System State Model](docs/architecture/system-state-model.md) |  |
| [Tool Admission Policy](docs/architecture/tool-admission-policy.md) |  |
| [Tool Fabric and MCP Plan](docs/architecture/tool-fabric-and-mcp-plan.md) |  |
| [Tool Lifecycle Policy](docs/architecture/tool-lifecycle-policy.md) |  |
| [Transition and Control Model](docs/architecture/transition-and-control-model.md) |  |
| [Trust KPIs and Drift Model](docs/architecture/trust-kpis-and-drift-model.md) |  |
| [Uncertainty and Confidence Model](docs/architecture/uncertainty-and-confidence-model.md) |  |
| [Workflow-Runtime ↔ Orchestrator Boundary](docs/architecture/workflow-orchestrator-boundary.md) |  |
| [Workflow Production Patterns](docs/architecture/workflow-production-patterns.md) |  |
| [Workflow Registry Model](docs/architecture/workflow-registry-model.md) |  |


---

## Architectural Decision Records (ADRs)

| Document | Summary |
|----------|---------|
| [ADR-001: computer is a monorepo, not a monolith](docs/adr/ADR-001-monorepo.md) |  |
| [ADR-002: AI cannot directly actuate hardware](docs/adr/ADR-002-ai-no-actuation.md) |  |
| [ADR-003: Home Assistant is an integration and UI plane, not the system of record](docs/adr/ADR-003-ha-not-system-of-record.md) |  |
| [ADR-004: MQTT is edge transport; PostgreSQL is control truth](docs/adr/ADR-004-mqtt-postgres.md) |  |
| [ADR-005: Rover precedes drone](docs/adr/ADR-005-rover-before-drone.md) |  |
| [ADR-006: Safety gates are required for all high-risk commands](docs/adr/ADR-006-safety-gates.md) |  |
| [ADR-007: All workflows are job/state-machine driven](docs/adr/ADR-007-job-state-machine.md) |  |
| [ADR-008: OSINT providers are optional adapters, not core dependencies](docs/adr/ADR-008-osint-optional.md) |  |
| [ADR-009: Device identity and broker authentication](docs/adr/ADR-009-device-identity.md) |  |
| [ADR-010: Normalized asset and capability model](docs/adr/ADR-010-capability-model.md) |  |
| [ADR-011: Computer includes a Personal Intelligence Plane separate from Site Operations](docs/adr/ADR-011-personal-intelligence-plane.md) |  |
| [ADR-012: Household identity, roles, and permissions model](docs/adr/ADR-012-household-identity.md) |  |
| [ADR-013: Personal memory is partitioned by person, household, and shared context](docs/adr/ADR-013-personal-memory-partitioning.md) |  |
| [ADR-014: Assistant actions are policy-tiered into personal, household, and site-control scopes](docs/adr/ADR-014-assistant-policy-tiers.md) |  |
| [ADR-015: Family assistant UX is separate from ops-web](docs/adr/ADR-015-family-assistant-ux-separate.md) |  |
| [ADR-016: Voice interactions route by intent class](docs/adr/ADR-016-voice-intent-routing.md) |  |
| [ADR-017: Durable Workflow Plane](docs/adr/ADR-017-durable-workflow-plane.md) |  |
| [ADR-018: Tool Fabric Plane — MCP as Universal Step 7a Interface](docs/adr/ADR-018-tool-fabric-plane.md) |  |
| [ADR-019: Authorization Evolution — RBAC v1 to ReBAC v2](docs/adr/ADR-019-authorization-evolution.md) |  |
| [ADR-020: Attention Plane — Delivery Decisions in Execution, Not UI](docs/adr/ADR-020-attention-plane.md) |  |
| [ADR-021: Local-First Sync — family-web Resilience](docs/adr/ADR-021-local-first-sync.md) |  |
| [ADR-022: Voice Fluency — v2 Contract and Shared-Device Rule](docs/adr/ADR-022-voice-fluency.md) |  |
| [ADR-023: AI Evaluation Plane — Behavioral Regression Gate](docs/adr/ADR-023-ai-eval-plane.md) |  |
| [ADR-024: Traceability Plane — OTEL + CRK trace_id Threading](docs/adr/ADR-024-traceability-plane.md) |  |
| [ADR-025: CRK is the Primary Request Execution Loop (No Second Lifecycle)](docs/adr/ADR-025-crk-primary-execution-loop.md) |  |
| [ADR-026: MCP is the Universal Tool Interface for Step 7a Only](docs/adr/ADR-026-mcp-universal-step-7a.md) |  |
| [ADR-027: All Long-Lived Tasks Must Use workflow-runtime](docs/adr/ADR-027-all-long-lived-tasks-use-workflow-runtime.md) |  |
| [ADR-028: Attention Decisions Are Part of Execution Step 9, Not UI](docs/adr/ADR-028-attention-decisions-step-9-not-ui.md) |  |
| [ADR-029: ExecutionContext is First-Class and Audited at Every Step](docs/adr/ADR-029-execution-context-first-class.md) |  |
| [ADR-030: Kernel Authority Model — Non-Overlapping Component Ownership](docs/adr/ADR-030-kernel-authority-model.md) |  |
| [ADR-031: workflow-runtime ↔ orchestrator Boundary Contract](docs/adr/ADR-031-workflow-orchestrator-boundary.md) |  |
| [ADR-032: Mode Transitions, Stickiness, and Shared-Device Ambiguity Rule](docs/adr/ADR-032-mode-transitions-stickiness-shared-device.md) |  |
| [ADR-033: ReBAC Authorization Evolution Strategy](docs/adr/ADR-033-rebac-authorization-evolution.md) |  |
| [ADR-034: Passkey-First Authentication with Approval-Grade Escalation for family-web](docs/adr/ADR-034-passkey-first-auth-family-web.md) |  |
| [ADR-035: Local-First Sync Scope and Device-Trust Prerequisites](docs/adr/ADR-035-local-first-sync-scope.md) |  |
| [ADR-036: Policy Tuning Requires PolicyImpactReport Before Replay, Replay Before Publish](docs/adr/ADR-036-policy-tuning-requires-impact-report-and-replay.md) |  |


---

## Product

| Document | Summary |
|----------|---------|
| [Assistant Capability Domains](docs/product/assistant-capability-domains.md) |  |
| [Assistant Surface Map](docs/product/assistant-surface-map.md) |  |
| [Assistant Tooling Specification](docs/product/assistant-tooling-spec.md) |  |
| [Assistant Trust Tiers](docs/product/assistant-trust-tiers.md) |  |
| [Attention and Escalation Policy](docs/product/attention-and-escalation-policy.md) |  |
| [Attention Decision Model](docs/product/attention-decision-model.md) |  |
| [Attention Memory Model](docs/product/attention-memory-model.md) |  |
| [Computer Assistant Charter](docs/product/computer-assistant-charter.md) |  |
| [Continuity and Follow-Up Model](docs/product/continuity-and-followup-model.md) |  |
| [Family Assistant Specification](docs/product/family-assistant-spec.md) |  |
| [Founder Decision Support Model](docs/product/founder-decision-support-model.md) |  |
| [Operating Modes: Founder Mode vs Family Mode](docs/product/founder-mode-vs-family-mode.md) |  |
| [Founder Operating Mode](docs/product/founder-operating-mode.md) |  |
| [Household Roles and Permissions](docs/product/household-roles-and-permissions.md) |  |
| [Memory Lifecycle Policy](docs/product/memory-lifecycle-policy.md) |  |
| [Mode Transition Rules](docs/product/mode-transition-rules.md) |  |
| [Multimodal Interaction Model](docs/product/multimodal-interaction-model.md) |  |
| [Open Loop Mathematics](docs/product/open-loop-mathematics.md) |  |
| [Personal Memory Specification](docs/product/personal-memory-spec.md) |  |
| [Policy Tuning Console](docs/product/policy-tuning-console.md) |  |
| [Voice Fluency Specification](docs/product/voice-fluency-spec.md) |  |
| [Voice Quality Engineering](docs/product/voice-quality-engineering.md) |  |


---

## Safety

| Document | Summary |
|----------|---------|
| [Actuation Policy](docs/safety/actuation-policy.md) |  |
| [Calibration Standard Operating Procedures](docs/safety/calibration-sops.md) |  |
| [Command Risk Classification](docs/safety/command-risk-classification.md) |  |
| [Degraded Mode Specification](docs/safety/degraded-mode-spec.md) |  |
| [Drift Remediation Policy](docs/safety/drift-remediation-policy.md) |  |
| [E-Stop and Fail-Safe Specification](docs/safety/e-stop-and-fail-safe.md) |  |
| [Emergency Mode Specification](docs/safety/emergency-mode-spec.md) |  |
| [Formal Invariants and Proof Obligations](docs/safety/formal-invariants-and-proof-obligations.md) |  |
| [Hardware Qualification Checklists](docs/safety/hardware-qualification-checklists.md) |  |


---

## Delivery

| Document | Summary |
|----------|---------|
| [Assistant Evaluation Plan](docs/delivery/assistant-eval-plan.md) |  |
| [Bootstrap Boundaries](docs/delivery/bootstrap-boundaries.md) |  |
| [CI Matrix](docs/delivery/ci-matrix.md) |  |
| [Experimental Design and Evaluation](docs/delivery/experimental-design-and-evaluation.md) |  |
| [Field Truth and Shadow Mode](docs/delivery/field-truth-and-shadow-mode.md) |  |
| [Hardware-in-Loop (HIL) Gate Plan](docs/delivery/hil-gate-plan.md) |  |
| [Policy Publish Gate](docs/delivery/policy-publish-gate.md) | **Rule 1:** No policy change may be published until it has been replayed against… |
| [Release Train](docs/delivery/release-train.md) |  |
| [Repo Bootstrap Specification](docs/delivery/repo-bootstrap-spec.md) |  |
| [Rollback and Restore Procedures](docs/delivery/rollback-and-restore.md) |  |


---

## Runbooks

_None yet._


---

## Standards and Templates

| Document | Description |
|----------|-------------|
| [documentation-style-guide.md](standards/documentation-style-guide.md) | Tone, heading hierarchy, diagrams, tables, length limits |
| [README.template.md](templates/README.template.md) | Canonical README template for services and packages |

---

## CLI Reference

See [docs/cli/command-reference.md](cli/command-reference.md) for all `computer` CLI commands, Taskfile tasks, and scenario scripts.

---

_Generated by `scripts/generate_docs_index.py`_
