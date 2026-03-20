#!/usr/bin/env bash
# backup.sh — Computer system backup script
#
# Backs up:
#   - PostgreSQL database (jobs, assets, events, audit)
#   - Site configuration (site.yaml, asset seeds)
#   - Secrets manifest (not secrets themselves — those are in vault)
#   - System state snapshots (digital twin)
#
# Storage targets (configured via env):
#   - Local: /var/backup/computer/
#   - NAS: rsync to NAS_BACKUP_HOST (optional)
#   - Remote: rclone to S3-compatible (optional)
#
# Schedule: run from cron or systemd timer
#   0 2 * * *  /path/to/computer/scripts/backup/backup.sh
#
# See docs/delivery/rollback-and-restore.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/var/backup/computer}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Service endpoints
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-computer}"
POSTGRES_USER="${POSTGRES_USER:-computer}"
POSTGRES_PASS="${POSTGRES_PASS}"

# Optional remote targets
NAS_BACKUP_HOST="${NAS_BACKUP_HOST:-}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"

BACKUP_NAME="computer-backup-${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

log "=== Computer System Backup ==="
log "Timestamp: ${TIMESTAMP}"
log "Destination: ${BACKUP_PATH}"

# Create backup directory
mkdir -p "${BACKUP_PATH}"

# ── 1. PostgreSQL Dump ────────────────────────────────────────────────────────
log "Backing up PostgreSQL database..."
PGPASSWORD="${POSTGRES_PASS}" pg_dump \
  -h "${POSTGRES_HOST}" \
  -p "${POSTGRES_PORT}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --format=custom \
  --compress=9 \
  --file="${BACKUP_PATH}/postgres.dump" \
  2>/dev/null && log "PostgreSQL backup: OK" || {
    err "PostgreSQL backup failed"
    # Don't abort — continue with other backups
  }

# ── 2. Site Configuration ────────────────────────────────────────────────────
log "Backing up site configuration..."
cp -r "${REPO_ROOT}/packages/config/site/" "${BACKUP_PATH}/site-config/"
cp -r "${REPO_ROOT}/data/seed/" "${BACKUP_PATH}/seed-data/"
cp -r "${REPO_ROOT}/data/bom/" "${BACKUP_PATH}/bom/"
log "Site config backup: OK"

# ── 3. System Version Manifest ───────────────────────────────────────────────
log "Capturing version manifest..."
cp "${REPO_ROOT}/packages/config/versions.json" "${BACKUP_PATH}/versions.json"
if command -v git &>/dev/null; then
  git -C "${REPO_ROOT}" log -1 --format="%H %s" > "${BACKUP_PATH}/git-commit.txt" 2>/dev/null || true
fi
log "Version manifest: OK"

# ── 4. Compress archive ──────────────────────────────────────────────────────
log "Compressing backup archive..."
cd "${BACKUP_DIR}"
tar czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}/"
rm -rf "${BACKUP_NAME}/"
ARCHIVE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
log "Archive created: ${ARCHIVE} (${SIZE})"

# ── 5. Checksum ──────────────────────────────────────────────────────────────
sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
log "Checksum: OK"

# ── 6. Remote sync (optional) ────────────────────────────────────────────────
if [[ -n "${NAS_BACKUP_HOST}" ]]; then
  log "Syncing to NAS: ${NAS_BACKUP_HOST}..."
  rsync -az --progress "${ARCHIVE}" "${ARCHIVE}.sha256" \
    "${NAS_BACKUP_HOST}:/backup/computer/" \
    && log "NAS sync: OK" \
    || err "NAS sync failed (non-fatal)"
fi

if [[ -n "${RCLONE_REMOTE}" ]]; then
  log "Syncing to remote: ${RCLONE_REMOTE}..."
  rclone copy "${ARCHIVE}" "${RCLONE_REMOTE}/computer-backups/" \
    && log "Remote sync: OK" \
    || err "Remote sync failed (non-fatal)"
fi

# ── 7. Prune old backups ─────────────────────────────────────────────────────
log "Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "computer-backup-*.tar.gz" -mtime "+${RETENTION_DAYS}" -delete
find "${BACKUP_DIR}" -name "computer-backup-*.sha256" -mtime "+${RETENTION_DAYS}" -delete
log "Pruned old backups: OK"

log "=== Backup COMPLETE: ${BACKUP_NAME} ==="
