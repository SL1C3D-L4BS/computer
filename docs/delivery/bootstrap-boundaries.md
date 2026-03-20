# Bootstrap Boundaries

Defines exactly what `./bootstrap.sh` brings up, what it leaves out of scope, and the dependency order it enforces.

## What bootstrap brings up

Bootstrap targets the **local development integration stack**. It does not provision production infrastructure.

### Tier 1 — Infrastructure (always first)

| Service | How started | Port | Health check |
|---------|-------------|------|-------------|
| PostgreSQL 18.3 | Docker Compose | 5432 | `pg_isready` |
| Redis 8.6 | Docker Compose | 6379 | `redis-cli ping` |
| Mosquitto 2.1.2 (MQTT) | Docker Compose | 1883, 8883 (TLS) | TCP connect |

Bootstrap polls until all three are healthy before proceeding.

### Tier 2 — Kernel

| Service | How started | Port | Health check |
|---------|-------------|------|-------------|
| digital-twin | `uv run` or Docker | 8001 | `GET /health` → 200 |
| orchestrator | `uv run` or Docker | 8002 | `GET /health` → 200 |

digital-twin runs migrations on startup. Bootstrap polls `/health` on both before proceeding.

### Tier 3 — API and ingest

| Service | How started | Port | Health check |
|---------|-------------|------|-------------|
| control-api | `uv run` or Docker | 8000 | `GET /health` → 200 |
| event-ingest | `uv run` or Docker | 8003 | `GET /health` → 200 |

### Tier 4 — Adapters and control services (optional in local dev)

Started with `--with-adapters` flag only. In bare-metal dev, skipped unless testing integration.

| Service | Flag |
|---------|------|
| ha-adapter | `--with-adapters` |
| frigate-adapter | `--with-adapters` |
| greenhouse-control | `--with-adapters` |
| hydro-control | `--with-adapters` |
| energy-engine | `--with-adapters` |

### Tier 5 — Assistant plane (optional in local dev)

Started with `--with-assistant` flag.

| Service | Port |
|---------|------|
| identity-service | 8010 |
| memory-service | 8011 |
| context-router | 8012 |
| model-router | 8013 |
| assistant-api | 8014 |

Requires Ollama running locally (not managed by bootstrap; operator must start it separately).

### Tier 6 — UX

| Service | How started | Port |
|---------|-------------|------|
| ops-web | `pnpm dev` (Next.js) | 3000 |
| family-web | `pnpm dev` (Next.js) | 3001 |

UX is optional in CI. Started with `--with-ux` flag.

## What bootstrap does NOT bring up

- Ollama / vLLM — operator starts manually
- Home Assistant — runs on dedicated host; not in compose
- Frigate — runs on dedicated host; not in compose
- ROS2 workspace — separate bring-up (`ros2 launch`)
- PX4 SITL — separate bring-up (`make px4_sitl gazebo`)
- Physical hardware (MCUs, rover, drone, cameras)
- Production Postgres / Redis (prod uses separate provisioning via Ansible)
- NVR / NAS storage

## Bootstrap environment prerequisites

Bootstrap verifies these are installed before starting:

```
node >= 24.0.0 (LTS)
python >= 3.14.0
uv >= 0.10.0
pnpm >= 10.0.0
docker >= 24.0.0
docker compose >= 2.0.0
```

Version numbers are checked against `packages/config/versions.json`. Bootstrap fails fast if any prerequisite is missing or out of range.

## Seed data

After Tier 2 is healthy, bootstrap runs:

```bash
uv run python -m digital_twin.seed --site=spokane
```

This loads:
- Zone definitions (greenhouse zones, land zones, structures)
- Asset stubs (pumps, relays, cameras — no real device connection required)
- Tariff config (Avista TOU)
- Frost calendar (WSU Spokane)
- Crop schedule stubs

## Environment files

Bootstrap generates `.env` files from `.env.template` files if they don't exist. It never overwrites existing `.env` files. Secrets (DB passwords, MQTT credentials, API keys) are generated as random defaults for local dev and printed to stdout once.

Never commit `.env` files. They are in `.gitignore`.

## Startup command

```bash
./bootstrap.sh                    # Core stack only
./bootstrap.sh --with-adapters    # + adapters and control services
./bootstrap.sh --with-assistant   # + assistant plane (requires Ollama)
./bootstrap.sh --with-ux          # + ops-web and family-web dev servers
./bootstrap.sh --full             # Everything except Ollama/HA/Frigate/ROS
```

Bootstrap exits with code 0 only when all requested tiers pass health checks.

## Related documents

- `docs/architecture/runtime-glue-and-cohesion.md` — startup order rationale
- `docs/delivery/repo-bootstrap-spec.md` — full bootstrap implementation spec
- `packages/config/versions.json` — version pins enforced at bootstrap
