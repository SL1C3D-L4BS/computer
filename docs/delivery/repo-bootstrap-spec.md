# Repo Bootstrap Specification

Complete specification for `./bootstrap.sh`. A developer or CI runner should be able to go from zero to a running local stack with a single command.

## Target

```bash
git clone git@github.com:SL1C3D-L4BS/computer.git
cd computer
./bootstrap.sh
```

Result: fully operational local integration stack — infrastructure up, kernel running, APIs serving, seed data loaded.

## Prerequisites verification

Bootstrap checks these before doing anything:

```bash
# Node.js
node_version=$(node --version | sed 's/v//')
required_node=$(jq -r '.node' packages/config/versions.json)
# fail if node_version < required_node (semver comparison)

# Python
python_version=$(python3 --version | awk '{print $2}')
required_python=$(jq -r '.python' packages/config/versions.json)

# uv
uv_version=$(uv --version | awk '{print $2}')
required_uv=$(jq -r '.uv' packages/config/versions.json)

# pnpm
pnpm_version=$(pnpm --version)
required_pnpm=$(jq -r '.pnpm' packages/config/versions.json)

# Docker
docker_version=$(docker version --format '{{.Server.Version}}')

# docker compose
docker compose version
```

If any prerequisite fails: print which one, print the expected version from `versions.json`, and exit 1. Never attempt to install missing prerequisites; that is the operator's responsibility.

## Step 1: Environment files

```bash
for template in $(find . -name ".env.template" -not -path "*/node_modules/*"); do
  target="${template%.template}"
  if [ ! -f "$target" ]; then
    cp "$template" "$target"
    # Replace placeholder secrets with random values for local dev
    sed -i "s/REPLACE_ME_POSTGRES_PASSWORD/$(openssl rand -hex 16)/g" "$target"
    sed -i "s/REPLACE_ME_REDIS_PASSWORD/$(openssl rand -hex 16)/g" "$target"
    sed -i "s/REPLACE_ME_MQTT_PASSWORD/$(openssl rand -hex 16)/g" "$target"
    sed -i "s/REPLACE_ME_JWT_SECRET/$(openssl rand -hex 32)/g" "$target"
    echo "Created $target with generated secrets"
  else
    echo "Skipping $target (already exists)"
  fi
done
```

## Step 2: Install dependencies

```bash
# JavaScript/TypeScript dependencies
pnpm install --frozen-lockfile

# Python dependencies (each Python service has its own uv workspace)
for pyproject in $(find apps services -name "pyproject.toml" -not -path "*/node_modules/*"); do
  dir=$(dirname "$pyproject")
  echo "Installing Python dependencies in $dir"
  uv sync --frozen --project "$dir"
done
```

## Step 3: Generate contracts

```bash
pnpm contracts:generate
```

This must run before starting any services, as generated types are imported at startup. If contracts generation fails, bootstrap exits 1.

## Step 4: Start infrastructure (Tier 1)

```bash
docker compose -f infra/docker/compose.infra.yml up -d

# Health poll: Postgres
wait_for_postgres() {
  local retries=30
  while ! docker compose -f infra/docker/compose.infra.yml exec -T postgres pg_isready -U computer > /dev/null 2>&1; do
    retries=$((retries - 1))
    if [ $retries -eq 0 ]; then echo "Postgres failed to start"; exit 1; fi
    sleep 2
  done
  echo "Postgres ready"
}

# Health poll: Redis
wait_for_redis() {
  local retries=30
  while ! docker compose -f infra/docker/compose.infra.yml exec -T redis redis-cli ping | grep -q PONG; do
    retries=$((retries - 1))
    if [ $retries -eq 0 ]; then echo "Redis failed to start"; exit 1; fi
    sleep 2
  done
  echo "Redis ready"
}

# Health poll: MQTT
wait_for_mqtt() {
  local retries=30
  while ! nc -z localhost 1883 > /dev/null 2>&1; do
    retries=$((retries - 1))
    if [ $retries -eq 0 ]; then echo "MQTT failed to start"; exit 1; fi
    sleep 2
  done
  echo "MQTT ready"
}

wait_for_postgres
wait_for_redis
wait_for_mqtt
```

## Step 5: Run database migrations

```bash
uv run --project apps/digital-twin alembic upgrade head
uv run --project apps/orchestrator alembic upgrade head
```

Migrations must succeed before starting kernel services.

## Step 6: Start kernel (Tier 2)

```bash
docker compose -f infra/docker/compose.kernel.yml up -d

wait_for_http() {
  local url=$1
  local service=$2
  local retries=30
  while ! curl -sf "$url" > /dev/null 2>&1; do
    retries=$((retries - 1))
    if [ $retries -eq 0 ]; then echo "$service failed to start"; exit 1; fi
    sleep 2
  done
  echo "$service ready"
}

wait_for_http "http://localhost:8001/health" "digital-twin"
wait_for_http "http://localhost:8002/health" "orchestrator"
```

## Step 7: Start API and ingest (Tier 3)

```bash
docker compose -f infra/docker/compose.api.yml up -d

wait_for_http "http://localhost:8000/health" "control-api"
wait_for_http "http://localhost:8003/health" "event-ingest"
```

## Step 8: Load seed data

```bash
uv run --project apps/digital-twin python -m digital_twin.seed --site=spokane
echo "Seed data loaded"
```

## Step 9: Optional tiers

```bash
if [[ "$*" == *"--with-adapters"* ]]; then
  docker compose -f infra/docker/compose.adapters.yml up -d
  echo "Adapters started"
fi

if [[ "$*" == *"--with-assistant"* ]]; then
  # Verify Ollama is running
  if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "WARNING: Ollama is not running. Start it before using assistant features."
    echo "  Install: https://ollama.ai"
    echo "  Start:   ollama serve"
    echo "  Model:   ollama pull qwen2.5:7b"
  fi
  docker compose -f infra/docker/compose.assistant.yml up -d
  wait_for_http "http://localhost:8010/health" "identity-service"
  wait_for_http "http://localhost:8011/health" "memory-service"
  wait_for_http "http://localhost:8012/health" "context-router"
  wait_for_http "http://localhost:8013/health" "model-router"
  wait_for_http "http://localhost:8014/health" "assistant-api"
fi

if [[ "$*" == *"--with-ux"* ]]; then
  pnpm --filter ops-web dev &
  pnpm --filter family-web dev &
  echo "UX dev servers started on :3000 (ops-web) and :3001 (family-web)"
fi
```

## Step 10: Final health summary

```bash
echo ""
echo "=== Computer Stack Health ==="
echo "Infrastructure:"
echo "  Postgres:    $(check_service http://localhost:5432 postgres)"
echo "  Redis:       $(check_service_redis)"
echo "  MQTT:        $(check_service_mqtt)"
echo ""
echo "Kernel:"
echo "  digital-twin: $(curl -sf http://localhost:8001/health | jq -r '.status')"
echo "  orchestrator: $(curl -sf http://localhost:8002/health | jq -r '.status')"
echo ""
echo "API:"
echo "  control-api:  $(curl -sf http://localhost:8000/health | jq -r '.status')"
echo "  event-ingest: $(curl -sf http://localhost:8003/health | jq -r '.status')"
echo ""
echo "Bootstrap complete. System is ready."
echo "  ops-web:     http://localhost:3000 (if --with-ux)"
echo "  control-api: http://localhost:8000"
echo "  API docs:    http://localhost:8000/docs"
```

## Bootstrap exit codes

| Code | Meaning |
|------|---------|
| 0 | All requested tiers healthy |
| 1 | Prerequisites failed |
| 2 | Dependency health check timeout |
| 3 | Migration failed |
| 4 | Seed data failed |
| 5 | Contract generation failed |

## Teardown

```bash
./bootstrap.sh --down
```

Stops and removes all containers. Does not delete Postgres volumes (data is preserved). Use `--down --clean` to also remove volumes (development reset).
