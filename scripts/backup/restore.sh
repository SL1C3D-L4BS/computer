#!/usr/bin/env bash
# restore.sh — Computer system restore script
#
# Restores from a backup archive produced by backup.sh.
# Usage: ./restore.sh <backup-archive.tar.gz> [--dry-run]
#
# What is restored:
#   - PostgreSQL database
#   - Site configuration
#   - Seed data
#
# CRITICAL: Run with all services stopped before restoring.
# See docs/delivery/rollback-and-restore.md for procedure.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup-archive.tar.gz> [--dry-run]"
  exit 1
fi

ARCHIVE="$1"
DRY_RUN="${2:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESTORE_DIR="/tmp/computer-restore-${TIMESTAMP}"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-computer}"
POSTGRES_USER="${POSTGRES_USER:-computer}"
POSTGRES_PASS="${POSTGRES_PASS}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

if [[ ! -f "${ARCHIVE}" ]]; then
  err "Archive not found: ${ARCHIVE}"
  exit 1
fi

log "=== Computer System Restore ==="
log "Archive: ${ARCHIVE}"
[[ "${DRY_RUN}" == "--dry-run" ]] && log "DRY RUN mode — no changes will be made"

# Verify checksum
if [[ -f "${ARCHIVE}.sha256" ]]; then
  log "Verifying archive checksum..."
  sha256sum -c "${ARCHIVE}.sha256" && log "Checksum: OK" || {
    err "Checksum verification FAILED"
    exit 1
  }
fi

# Extract archive
log "Extracting archive..."
mkdir -p "${RESTORE_DIR}"
tar xzf "${ARCHIVE}" -C "${RESTORE_DIR}"
BACKUP_DIR=$(ls "${RESTORE_DIR}/" | head -1)
BACKUP_PATH="${RESTORE_DIR}/${BACKUP_DIR}"

log "Extracted to: ${BACKUP_PATH}"
log "Contents: $(ls ${BACKUP_PATH})"

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
  log "DRY RUN: Would restore from ${BACKUP_PATH}"
  log "DRY RUN: Would restore PostgreSQL from ${BACKUP_PATH}/postgres.dump"
  log "DRY RUN: Would restore site config from ${BACKUP_PATH}/site-config/"
  rm -rf "${RESTORE_DIR}"
  log "DRY RUN complete — no changes made"
  exit 0
fi

# Confirm before destructive restore
echo ""
echo "WARNING: This will OVERWRITE the current database and configuration."
echo "Archive: ${ARCHIVE}"
echo ""
read -rp "Type 'CONFIRM' to proceed: " CONFIRM
if [[ "${CONFIRM}" != "CONFIRM" ]]; then
  log "Restore cancelled"
  rm -rf "${RESTORE_DIR}"
  exit 0
fi

# ── 1. Restore PostgreSQL ────────────────────────────────────────────────────
if [[ -f "${BACKUP_PATH}/postgres.dump" ]]; then
  log "Restoring PostgreSQL database..."
  PGPASSWORD="${POSTGRES_PASS}" pg_restore \
    -h "${POSTGRES_HOST}" \
    -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --clean \
    --if-exists \
    "${BACKUP_PATH}/postgres.dump" \
    && log "PostgreSQL restore: OK" \
    || err "PostgreSQL restore had errors (check above)"
fi

# ── 2. Restore site config ───────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -d "${BACKUP_PATH}/site-config/" ]]; then
  log "Restoring site configuration..."
  cp -r "${BACKUP_PATH}/site-config/" "${REPO_ROOT}/packages/config/site/"
  log "Site config restore: OK"
fi

if [[ -d "${BACKUP_PATH}/seed-data/" ]]; then
  log "Restoring seed data..."
  cp -r "${BACKUP_PATH}/seed-data/" "${REPO_ROOT}/data/seed/"
  log "Seed data restore: OK"
fi

# Cleanup
rm -rf "${RESTORE_DIR}"

log "=== Restore COMPLETE ==="
log "Next steps:"
log "  1. Verify services with: ./bootstrap.sh"
log "  2. Run health checks: task bootstrap"
log "  3. Validate: task ci:milestone-1"
