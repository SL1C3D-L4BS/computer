# Feature Flag Strategy

Defines which features use flags, how flags are managed, and how optional modules are enabled.

## Why feature flags

Some Computer features are:
1. **Optional modules** — OSINT, voice, robotics — not every deployment needs them.
2. **Phased rollouts** — new assistant capabilities during Phase E2 development.
3. **Site-specific** — features only applicable to certain sites or hardware configurations.
4. **Experimental** — features under active development, not yet production-stable.

Feature flags allow the core system to ship without optional modules and to enable them selectively.

## Flag types

| Type | Managed in | Changed by |
|------|-----------|-----------|
| **Module flags** | `packages/config/site.yaml` | Operator via config edit + redeploy |
| **Feature flags** | `packages/config/features.yaml` | Operator via config edit + redeploy |
| **Experimental flags** | Environment variable | Developer via `.env` |

No runtime flag toggling via API in v1. Flags require a config change and service restart. This is intentional: runtime toggles complicate audit and make behavior less predictable.

## Module flags (site.yaml)

```yaml
features:
  osint_enabled: true           # Enable OSINT ingestion (optional module)
  voice_enabled: true           # Enable voice-gateway
  robotics_enabled: false       # Enable rover and drone control
  drone_enabled: false          # Enable drone specifically (requires robotics_enabled)
  assistant_enabled: true       # Enable personal intelligence plane
  family_web_enabled: true      # Enable family-web UI
  energy_management_enabled: true
  greenhouse_enabled: true
  hydroponics_enabled: true
```

When a module flag is `false`:
- The corresponding service is not started by bootstrap.
- The corresponding routes in control-api return 404 or 503 with a `feature_disabled` error code.
- The ops-web UI hides the corresponding panels.

## Feature flags (features.yaml)

```yaml
assistant:
  memory_enabled: true
  proactive_briefings: false    # Morning briefings (experimental in Phase E2)
  multi_model_routing: false    # Route between multiple models (experimental)
  voice_transcription: true
  family_mode: true
  work_mode: true

ops:
  ai_job_proposals: true        # AI can propose jobs (Phase E)
  ai_auto_approve_low: false    # AI can auto-approve LOW risk jobs (Phase E+; off by default)
  laser_weeding: false          # Late-stage R&D; not in Phase F
  drone_autonomous: false       # Drone autonomous missions (Phase G; off by default)
  swarm_mode: false             # Late-stage R&D; never enabled in v1
```

## Experimental flags (environment variables)

```bash
# .env.local (not committed)
EXPERIMENTAL_CREW_AI=false       # Enable CrewAI at advisory layer
EXPERIMENTAL_VLLM=false          # Use vLLM instead of Ollama
EXPERIMENTAL_NATS=false          # Replace MQTT with NATS (not in v1)
```

## Flag enforcement in code

Services check flags at startup and cache them:

```python
# packages/sdk/computer_sdk/features.py
from computer_sdk.config import features

if not features.is_enabled("robotics_enabled"):
    logger.info("Robotics module disabled; rover and drone routes will return 503")
    # Routes are still mounted but return FeatureDisabledError
```

Control services that are not enabled should not be started at all (handled by compose profiles and bootstrap flags).

## Compose profiles

Docker Compose uses profiles to manage optional modules:

```yaml
# infra/docker/compose.adapters.yml
services:
  osint-ingest:
    profiles: ["osint"]
  voice-gateway:
    profiles: ["voice"]
  rover-control:
    profiles: ["robotics"]
  drone-control:
    profiles: ["robotics", "drone"]
```

Bootstrap passes the appropriate profiles based on site.yaml flags:

```bash
# In bootstrap.sh
COMPOSE_PROFILES=""
[[ "$osint_enabled" == "true" ]] && COMPOSE_PROFILES="${COMPOSE_PROFILES},osint"
[[ "$voice_enabled" == "true" ]] && COMPOSE_PROFILES="${COMPOSE_PROFILES},voice"
[[ "$robotics_enabled" == "true" ]] && COMPOSE_PROFILES="${COMPOSE_PROFILES},robotics"

docker compose --profile "${COMPOSE_PROFILES#,}" up -d
```

## Flag audit

Any change to a feature flag must be:
1. Committed to the repo (flags are in version-controlled config).
2. Logged in RELEASES.md if it changes system behavior.
3. Communicated to household members if it affects assistant capabilities.

No silent flag changes.
