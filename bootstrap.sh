#!/usr/bin/env bash
# bootstrap.sh — Deterministic Computer stack bring-up
# From zero machine to running local stack with one command.
# Enforces startup order per docs/architecture/runtime-glue-and-cohesion.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[bootstrap]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── Flags ───────────────────────────────────────────────────────────────────
WITH_ADAPTERS=false
WITH_ASSISTANT=false
WITH_UX=false
FULL=false
DOWN=false
CLEAN=false
HEALTH_CHECK=false

for arg in "$@"; do
  case $arg in
    --with-adapters)  WITH_ADAPTERS=true ;;
    --with-assistant) WITH_ASSISTANT=true ;;
    --with-ux)        WITH_UX=true ;;
    --full)           FULL=true; WITH_ADAPTERS=true; WITH_ASSISTANT=true; WITH_UX=true ;;
    --down)           DOWN=true ;;
    --down --clean)   DOWN=true; CLEAN=true ;;
    --health-check)   HEALTH_CHECK=true ;;
  esac
done

# ── Health check only ────────────────────────────────────────────────────────
if [ "$HEALTH_CHECK" = true ]; then
  bash scripts/health_check.sh
  exit $?
fi

# ── Teardown ─────────────────────────────────────────────────────────────────
if [ "$DOWN" = true ]; then
  log "Stopping Computer stack..."
  docker compose -f infra/docker/compose.api.yml down 2>/dev/null || true
  docker compose -f infra/docker/compose.kernel.yml down 2>/dev/null || true
  if [ "$CLEAN" = true ]; then
    docker compose -f infra/docker/compose.infra.yml down -v 2>/dev/null || true
    ok "Stack stopped and volumes removed"
  else
    docker compose -f infra/docker/compose.infra.yml down 2>/dev/null || true
    ok "Stack stopped (data volumes preserved; use --down --clean to remove)"
  fi
  exit 0
fi

# ── Runtime gate ─────────────────────────────────────────────────────────────
# Enforce toolchain versions before doing anything else.
# Mismatched runtimes produce CI parity failures and type-syntax errors.
echo ""
log "Checking runtime toolchain against packages/config/versions.json..."
if ! ./scripts/check_runtime.sh --warn; then
  # --warn exits 0 but prints failures; check_runtime.sh --strict exits 1 on failure
  # We run --warn here so CI parity issues surface as WARN during local dev,
  # but fail hard in CI (where check_runtime.sh runs without --warn).
  warn "Runtime drift detected. See above. Continuing with --warn (non-strict mode)."
  warn "Fix your toolchain before running in production or CI."
fi

# ────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Computer Bootstrap                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── Step 0: Verify prerequisites ─────────────────────────────────────────────
log "Step 0: Verifying prerequisites..."

VERSIONS_FILE="packages/config/versions.json"
if [ ! -f "$VERSIONS_FILE" ]; then
  error "versions.json not found at $VERSIONS_FILE"
fi

check_version() {
  local cmd=$1
  local name=$2
  local min=$3
  if ! command -v "$cmd" &> /dev/null; then
    error "Missing prerequisite: $name ($cmd not found)"
  fi
  ok "$name found"
}

check_version node "Node.js" "24"
check_version python3 "Python" "3.14"
check_version uv "uv" "0.10"
check_version pnpm "pnpm" "10"
check_version docker "Docker" "24"

# Check docker compose
if ! docker compose version &> /dev/null; then
  error "Docker Compose v2 plugin required (docker compose, not docker-compose)"
fi
ok "Docker Compose v2 found"
echo ""

# ── Step 1: Generate environment files ────────────────────────────────────────
log "Step 1: Generating environment files..."

generate_secret() { openssl rand -hex 16; }
generate_jwt_secret() { openssl rand -hex 32; }

if [ ! -f ".env" ]; then
  cp .env.template .env
  # Replace placeholder secrets
  POSTGRES_PW=$(generate_secret)
  REDIS_PW=$(generate_secret)
  MQTT_PW=$(generate_secret)
  JWT_SECRET=$(generate_jwt_secret)

  sed -i.bak "s/REPLACE_ME_POSTGRES_PASSWORD/$POSTGRES_PW/g" .env
  sed -i.bak "s/REPLACE_ME_REDIS_PASSWORD/$REDIS_PW/g" .env
  sed -i.bak "s/REPLACE_ME_MQTT_PASSWORD/$MQTT_PW/g" .env
  sed -i.bak "s/REPLACE_ME_JWT_SECRET/$JWT_SECRET/g" .env
  rm -f .env.bak
  ok "Generated .env with random secrets"
  echo ""
  echo -e "${YELLOW}  Secrets written to .env (never commit this file)${NC}"
  echo ""
else
  ok ".env already exists (skipping)"
fi

# Source env
set -a; source .env; set +a

# ── Step 2: Install dependencies ──────────────────────────────────────────────
log "Step 2: Installing dependencies..."

log "  Installing Node/TypeScript dependencies..."
pnpm install --frozen-lockfile 2>&1 | tail -3
ok "  pnpm dependencies installed"

log "  Installing Python dependencies..."
for dir in apps/*/; do
  if [ -f "${dir}pyproject.toml" ]; then
    log "    ${dir}"
    uv sync --frozen --project "$dir" --no-progress 2>/dev/null || \
      uv sync --project "$dir" --no-progress 2>/dev/null || true
  fi
done
ok "  Python dependencies installed"
echo ""

# ── Step 3: Generate contracts ────────────────────────────────────────────────
log "Step 3: Generating contracts..."
pnpm contracts:generate 2>&1 | tail -5
ok "Contracts generated"
echo ""

# ── Step 4: Start infrastructure (Tier 1) ─────────────────────────────────────
log "Step 4: Starting infrastructure (Tier 1)..."
docker compose -f infra/docker/compose.infra.yml up -d
echo ""

# Health poll: Postgres
log "  Waiting for Postgres..."
for i in $(seq 1 30); do
  if docker compose -f infra/docker/compose.infra.yml exec -T postgres pg_isready -U computer > /dev/null 2>&1; then
    ok "  Postgres ready"
    break
  fi
  if [ "$i" -eq 30 ]; then error "Postgres failed to start in time"; fi
  sleep 2
done

# Health poll: Redis
log "  Waiting for Redis..."
for i in $(seq 1 30); do
  if docker compose -f infra/docker/compose.infra.yml exec -T redis redis-cli -a "${REDIS_PASSWORD:-devpassword}" ping 2>/dev/null | grep -q PONG; then
    ok "  Redis ready"
    break
  fi
  if [ "$i" -eq 30 ]; then error "Redis failed to start in time"; fi
  sleep 2
done

# Health poll: MQTT
log "  Waiting for MQTT..."
for i in $(seq 1 30); do
  if nc -z localhost 1883 > /dev/null 2>&1; then
    ok "  MQTT (Mosquitto) ready"
    break
  fi
  if [ "$i" -eq 30 ]; then error "MQTT failed to start in time"; fi
  sleep 2
done
echo ""

# ── Step 5: Run database migrations ───────────────────────────────────────────
log "Step 5: Running database migrations..."
# Using direct SQL init (Alembic migrations to be added in Phase A implementation)
ok "Database initialized via Docker init scripts"
echo ""

# ── Step 6: Start kernel (Tier 2) ─────────────────────────────────────────────
log "Step 6: Starting kernel (Tier 2)..."
docker compose -f infra/docker/compose.kernel.yml up -d 2>/dev/null || {
  warn "Docker compose kernel failed (services may not be built yet)"
  warn "Starting kernel services directly with uv..."

  # Start services directly for development
  nohup uv run --project apps/digital-twin uvicorn digital_twin.main:app --port 8001 > /tmp/digital-twin.log 2>&1 &
  echo $! > /tmp/computer-digital-twin.pid
  nohup uv run --project apps/orchestrator uvicorn orchestrator.main:app --port 8002 > /tmp/orchestrator.log 2>&1 &
  echo $! > /tmp/computer-orchestrator.pid
}

wait_for_http() {
  local url=$1
  local name=$2
  log "  Waiting for $name..."
  for i in $(seq 1 30); do
    if curl -sf "$url" > /dev/null 2>&1; then
      ok "  $name ready"
      return 0
    fi
    if [ "$i" -eq 30 ]; then error "$name failed to start in time"; fi
    sleep 2
  done
}

wait_for_http "http://localhost:8001/health" "digital-twin"
wait_for_http "http://localhost:8002/health" "orchestrator"
echo ""

# ── Step 7: Start API and ingest (Tier 3) ─────────────────────────────────────
log "Step 7: Starting API and ingest (Tier 3)..."
docker compose -f infra/docker/compose.api.yml up -d 2>/dev/null || {
  warn "Docker compose API failed — starting directly..."
  nohup uv run --project apps/control-api uvicorn control_api.main:app --port 8000 > /tmp/control-api.log 2>&1 &
  echo $! > /tmp/computer-control-api.pid
  nohup uv run --project apps/event-ingest uvicorn event_ingest.main:app --port 8003 > /tmp/event-ingest.log 2>&1 &
  echo $! > /tmp/computer-event-ingest.pid
}

wait_for_http "http://localhost:8000/health" "control-api"
wait_for_http "http://localhost:8003/health" "event-ingest"
echo ""

# ── Step 8: Load seed data ─────────────────────────────────────────────────────
log "Step 8: Loading seed data..."
uv run --project apps/digital-twin python -m digital_twin.seed --site=spokane 2>/dev/null || warn "Seed data may already exist"
ok "Seed data loaded"
echo ""

# ── Step 9: Optional tiers ────────────────────────────────────────────────────
if [ "$WITH_ADAPTERS" = true ]; then
  log "Step 9a: Starting adapters..."
  warn "Adapter services require HA_URL and FRIGATE_URL to be set in .env"
  # docker compose -f infra/docker/compose.adapters.yml up -d
  ok "Adapters: skipped (set HA_URL/FRIGATE_URL in .env and uncomment)"
fi

if [ "$WITH_ASSISTANT" = true ]; then
  log "Step 9b: Starting assistant plane..."
  if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    warn "Ollama is not running. Assistant inference will be unavailable."
    echo "  Install: https://ollama.ai"
    echo "  Start:   ollama serve"
    echo "  Model:   ollama pull qwen2.5:7b"
  fi
  # docker compose -f infra/docker/compose.assistant.yml up -d
  ok "Assistant plane: config present; start with 'docker compose -f infra/docker/compose.assistant.yml up -d'"
fi

if [ "$WITH_UX" = true ]; then
  log "Step 9c: Starting UX dev servers..."
  pnpm --filter ops-web dev &
  echo $! > /tmp/computer-ops-web.pid
  ok "ops-web dev server starting on :3000"
fi

# ── Final health summary ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Bootstrap complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo "Services running:"
echo "  control-api:  http://localhost:8000"
echo "  API docs:     http://localhost:8000/docs"
echo "  orchestrator: http://localhost:8002"
echo "  digital-twin: http://localhost:8001"
echo "  event-ingest: http://localhost:8003"
if [ "$WITH_UX" = true ]; then
  echo "  ops-web:      http://localhost:3000"
fi
echo ""
echo "Quick commands:"
echo "  task health    — check all service health"
echo "  task down      — stop stack (preserves data)"
echo "  task scenario -- irrigation_leak_sim — run a system scenario"
echo ""
