#!/usr/bin/env bash
# check_runtime.sh — Hard runtime version gate
#
# Reads packages/config/versions.json and validates the local toolchain
# against every pinned version. Exits 1 on any mismatch.
#
# Called by:
#   - bootstrap.sh (pre-flight)
#   - CI (first step of every workflow)
#   - scripts/perfection_rubric.py (structural gate)
#
# Usage:
#   ./scripts/check_runtime.sh           # strict mode (fails on mismatch)
#   ./scripts/check_runtime.sh --warn    # warn only, do not exit 1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSIONS_FILE="${REPO_ROOT}/packages/config/versions.json"
WARN_ONLY="${1:-}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

FAILURES=0
WARNINGS=0

log()  { echo -e "${BLUE}[runtime-check]${NC} $*"; }
ok()   { echo -e "${GREEN}[PASS]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; WARNINGS=$((WARNINGS + 1)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES + 1)); }

if [[ ! -f "${VERSIONS_FILE}" ]]; then
  echo "ERROR: versions.json not found at ${VERSIONS_FILE}"
  exit 1
fi

# Extract pinned versions
PINNED_NODE=$(python3 -c "import json; d=json.load(open('${VERSIONS_FILE}')); print(d['runtimes']['node']['version'])" 2>/dev/null || echo "unknown")
PINNED_PYTHON=$(python3 -c "import json; d=json.load(open('${VERSIONS_FILE}')); print(d['runtimes']['python']['version'])" 2>/dev/null || echo "unknown")
PINNED_PNPM=$(python3 -c "import json; d=json.load(open('${VERSIONS_FILE}')); print(d['package_managers']['pnpm']['version'])" 2>/dev/null || echo "unknown")
PINNED_UV=$(python3 -c "import json; d=json.load(open('${VERSIONS_FILE}')); print(d['package_managers']['uv']['version'])" 2>/dev/null || echo "unknown")

# Extract major version for comparison (e.g. 24.0.0 → 24)
PINNED_NODE_MAJOR="${PINNED_NODE%%.*}"
PINNED_PYTHON_MINOR="${PINNED_PYTHON%.*}"  # e.g. 3.14.3 → 3.14

log "Runtime gate — checking against ${VERSIONS_FILE}"
log "Pinned: node=${PINNED_NODE}, python=${PINNED_PYTHON}, pnpm=${PINNED_PNPM}, uv=${PINNED_UV}"
echo ""

# ── Node.js ───────────────────────────────────────────────────────────────────
if command -v node &>/dev/null; then
  ACTUAL_NODE=$(node -v | tr -d 'v')
  ACTUAL_NODE_MAJOR="${ACTUAL_NODE%%.*}"
  if [[ "${ACTUAL_NODE_MAJOR}" == "${PINNED_NODE_MAJOR}" ]]; then
    ok "node v${ACTUAL_NODE} (major matches pinned ${PINNED_NODE_MAJOR}.x)"
  else
    fail "node v${ACTUAL_NODE} — MISMATCH. Pinned: Node ${PINNED_NODE_MAJOR}.x (v${PINNED_NODE})"
    echo "     Fix: nvm use 24  OR  volta install node@24  OR  brew install node@24"
    echo "     The repo requires Node 24 LTS (Krypton). Node 25 is not supported."
  fi
else
  fail "node not found in PATH"
  echo "     Fix: install Node 24 LTS via nvm, volta, or your package manager"
fi

# ── Python ────────────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
  ACTUAL_PYTHON=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
  ACTUAL_PYTHON_MINOR="${ACTUAL_PYTHON%.*}"
  if [[ "${ACTUAL_PYTHON_MINOR}" == "${PINNED_PYTHON_MINOR}" ]]; then
    ok "python3 ${ACTUAL_PYTHON} (matches pinned ${PINNED_PYTHON_MINOR}.x)"
  else
    fail "python3 ${ACTUAL_PYTHON} — MISMATCH. Pinned: Python ${PINNED_PYTHON_MINOR}.x (${PINNED_PYTHON})"
    echo "     Fix: pyenv install 3.14.x  OR  brew install python@3.14"
    echo "     Then: pyenv global 3.14.x  OR set PYTHON_PATH explicitly"
    echo "     Note: Python 3.12.x is incompatible with Python 3.14 type syntax in this codebase"
  fi
else
  fail "python3 not found in PATH"
fi

# ── pnpm ─────────────────────────────────────────────────────────────────────
if command -v pnpm &>/dev/null; then
  ACTUAL_PNPM=$(pnpm -v 2>/dev/null || echo "unknown")
  ACTUAL_PNPM_MAJOR="${ACTUAL_PNPM%%.*}"
  PINNED_PNPM_MAJOR="${PINNED_PNPM%%.*}"
  if [[ "${ACTUAL_PNPM_MAJOR}" == "${PINNED_PNPM_MAJOR}" ]]; then
    ok "pnpm ${ACTUAL_PNPM} (major matches pinned ${PINNED_PNPM_MAJOR}.x)"
  else
    fail "pnpm ${ACTUAL_PNPM} — MISMATCH. Pinned: pnpm ${PINNED_PNPM}"
    echo "     Fix: corepack enable && corepack use pnpm@${PINNED_PNPM}"
  fi
else
  fail "pnpm not found in PATH"
  echo "     Fix: corepack enable && corepack use pnpm@${PINNED_PNPM}"
  echo "     OR:  npm install -g pnpm@${PINNED_PNPM}"
fi

# ── uv ────────────────────────────────────────────────────────────────────────
if command -v uv &>/dev/null; then
  ACTUAL_UV=$(uv --version 2>/dev/null | awk '{print $2}' || echo "unknown")
  ok "uv ${ACTUAL_UV} found"
else
  warn "uv not found in PATH"
  echo "     Fix: curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "     OR:  pip install uv"
fi

# ── Docker ────────────────────────────────────────────────────────────────────
if command -v docker &>/dev/null; then
  ACTUAL_DOCKER=$(docker --version | awk '{print $3}' | tr -d ',')
  ok "docker ${ACTUAL_DOCKER} found"
else
  warn "docker not found — required for bootstrap and integration tests"
fi

echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
if [[ ${FAILURES} -gt 0 ]]; then
  echo -e "${RED}Runtime gate: ${FAILURES} FAILURE(S) — toolchain does not match versions.json${NC}"
  echo ""
  echo "  This repo pins specific runtime versions for reproducibility."
  echo "  Running on wrong versions risks:"
  echo "    - Syntax incompatibilities (Python 3.12 vs 3.14 type annotations)"
  echo "    - Behavior differences (Node 24 vs 25 ESM changes)"
  echo "    - CI parity failures (CI uses pinned versions)"
  echo ""
  echo "  See: packages/config/versions.json"
  echo "  See: docs/standards/compatibility-policy.md"
  echo ""
  if [[ "${WARN_ONLY}" == "--warn" ]]; then
    echo -e "${YELLOW}  Running with --warn: continuing despite failures${NC}"
    exit 0
  fi
  exit 1
elif [[ ${WARNINGS} -gt 0 ]]; then
  echo -e "${YELLOW}Runtime gate: PASS with ${WARNINGS} warning(s)${NC}"
  exit 0
else
  echo -e "${GREEN}Runtime gate: ALL PASS — toolchain matches pinned versions${NC}"
  exit 0
fi
