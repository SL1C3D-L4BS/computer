#!/usr/bin/env bash
# Health check script — checks all services and reports status

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

check_http() {
  local url=$1
  local name=$2
  if curl -sf "$url" > /dev/null 2>&1; then
    local status=$(curl -sf "$url" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status', 'ok'))" 2>/dev/null || echo "ok")
    if [ "$status" = "ok" ]; then
      echo -e "  ${GREEN}✓${NC} $name"
    else
      echo -e "  ${YELLOW}⚠${NC} $name (degraded)"
    fi
  else
    echo -e "  ${RED}✗${NC} $name (unreachable)"
  fi
}

check_tcp() {
  local host=$1
  local port=$2
  local name=$3
  if nc -z "$host" "$port" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} $name"
  else
    echo -e "  ${RED}✗${NC} $name (unreachable)"
  fi
}

echo "=== Computer Stack Health ==="
echo ""

echo "Infrastructure:"
check_tcp localhost 5432 "PostgreSQL :5432"
check_tcp localhost 6379 "Redis :6379"
check_tcp localhost 1883 "MQTT (Mosquitto) :1883"

echo ""
echo "Kernel:"
check_http http://localhost:8001/health "digital-twin :8001"
check_http http://localhost:8002/health "orchestrator :8002"

echo ""
echo "API:"
check_http http://localhost:8000/health "control-api :8000"
check_http http://localhost:8003/health "event-ingest :8003"

echo ""
echo "Assistant:"
check_http http://localhost:8010/health "identity-service :8010"
check_http http://localhost:8011/health "memory-service :8011"
check_http http://localhost:8012/health "context-router :8012"
check_http http://localhost:8013/health "model-router :8013"
check_http http://localhost:8014/health "assistant-api :8014"

echo ""
echo "UX:"
check_tcp localhost 3000 "ops-web :3000"
check_tcp localhost 3001 "family-web :3001"
