# Release Classes

Every service, workflow, and deployment belongs to a named release class. The class determines what testing and signoff is required before deployment.

## Class definitions

| Class | Meaning | Required gates before deploy |
|-------|---------|------------------------------|
| `dev` | Development only; not for production use | None |
| `sim-stable` | Passes simulation gates; may run in sim environments | Contract gate + Safety gate + Sim gate |
| `site-stable` | Safe for site deployment (greenhouse, energy, security) | All of sim-stable + Audit gate + Integration tests |
| `robotics-stable` | Rover/drone paths pass SITL/HIL | All of site-stable + Robotics gate + HIL runbook |
| `field-qualified` | Full field deployment with backup/restore and operator signoff | All of robotics-stable + Release gate + Backup verified + Operator sign-off |

## Assignment rules

Services are assigned a maximum class they may reach:

| Service / component | Maximum class | Notes |
|--------------------|--------------|-------|
| ops-web, family-web, chat | `site-stable` | UI-only; no actuation |
| control-api | `site-stable` | API surface; no direct actuation |
| orchestrator | `field-qualified` | Core kernel; highest bar |
| event-ingest | `site-stable` | Read-only from hardware perspective |
| digital-twin | `site-stable` | Asset registry |
| greenhouse-control, hydro-control, energy-engine | `site-stable` | Physical actuation; no robotics |
| ha-adapter, frigate-adapter | `site-stable` | Integration adapters |
| rover-control | `field-qualified` | Physical autonomy |
| drone-control | `field-qualified` | Physical autonomy; highest risk |
| assistant-api, model-router, context-router | `site-stable` | No direct actuation |
| memory-service, identity-service | `site-stable` | Data services |
| voice-gateway | `site-stable` | Interface only |

## Promotion flow

```
dev → sim-stable → site-stable → robotics-stable → field-qualified
```

A service cannot skip classes. Promotion requires all gates of the target class to pass on a release candidate.

## Class tagging

Release tags use the class as a prefix:
```
sim-stable/orchestrator/v0.2.0
site-stable/greenhouse-control/v1.0.0
field-qualified/rover-control/v0.1.0
```

Docker images are tagged with the same prefix. Deployment manifests specify minimum required class for each environment.

## Rollback policy per class

| Class | Rollback mechanism | Rollback time target |
|-------|-------------------|---------------------|
| `dev` | None required | N/A |
| `sim-stable` | Git revert + redeploy | < 30 min |
| `site-stable` | Previous image tag + DB migration rollback | < 15 min |
| `robotics-stable` | Previous image + config snapshot restore | < 15 min |
| `field-qualified` | Full backup restore procedure | < 60 min; procedure in runbook |

All rollbacks are documented in `docs/runbooks/rollback-procedures.md`.

## Related documents

- `docs/standards/compatibility-policy.md` — which versions are allowed in each class
- `docs/delivery/release-train.md` — release cadence and window management
- `docs/delivery/rollback-and-restore.md` — rollback procedures per class
