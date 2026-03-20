# Rollback and Restore Procedures

Defines rollback procedures per release class and restore procedures for backup/DR scenarios.

## Rollback procedures

### Service rollback (sim-stable / site-stable)

```bash
# 1. Identify previous version from RELEASES.md
previous_version="v1.1.3"
service="orchestrator"

# 2. Pull previous image
docker pull ghcr.io/sl1c3d-labs/computer-${service}:site-stable-${previous_version}

# 3. Update compose override
cat > infra/docker/overrides/${service}.override.yml << EOF
services:
  ${service}:
    image: ghcr.io/sl1c3d-labs/computer-${service}:site-stable-${previous_version}
EOF

# 4. Restart service
docker compose -f infra/docker/compose.kernel.yml \
  -f infra/docker/overrides/${service}.override.yml \
  up -d ${service}

# 5. Verify health
curl -sf http://localhost:8002/health | jq .

# 6. Log rollback in RELEASES.md
echo "ROLLBACK: ${service} rolled back from v1.2.0 to ${previous_version} by $(whoami) at $(date)" >> RELEASES.md
```

**Time target**: < 15 minutes for site-stable services.

### Database migration rollback

```bash
# Alembic down migration
uv run --project apps/orchestrator alembic downgrade -1

# Verify schema
uv run --project apps/orchestrator alembic current
```

Database rollback requires:
1. Service is stopped before downgrading migrations.
2. If migration was destructive (dropped columns/tables), restore from backup instead.
3. All migrations are forward-only by default; destructive rollbacks require explicit backup restore.

### Robotics-stable rollback

Same as service rollback, plus:
1. Verify SITL still passes on the rollback version.
2. Notify operator of rollback reason.
3. Document in RELEASES.md with SITL pass confirmation.

### Field-qualified rollback

Full rollback requires:
1. Stop all active robot missions (operator action).
2. Wait for all jobs in EXECUTING state to complete or abort.
3. Roll back service (same as site-stable procedure).
4. Roll back DB migration if needed.
5. Restore from last verified backup if data integrity is in question.
6. Re-run HIL smoke test before resuming autonomous operations.

**Time target**: < 60 minutes.

## Backup and restore

### Backup schedule

| Data | Method | Frequency | Retention | Storage |
|------|--------|-----------|-----------|---------|
| PostgreSQL (WAL) | pg_basebackup + WAL archive | Continuous | 30 days | NAS |
| PostgreSQL (dump) | pg_dump | Daily at 2am | 90 days | NAS + off-site |
| Redis snapshot | RDB dump | Every 4 hours | 7 days | NAS |
| Site config (packages/config/) | Git (already versioned) | On commit | Indefinite | GitHub |
| Infra config (compose, Ansible) | Git (already versioned) | On commit | Indefinite | GitHub |
| HA config | HA backup | Daily | 30 days | NAS |
| Frigate recordings | Rolling retention | Per Frigate config | 30 days default | NAS/HDD |
| Digital-twin state | Postgres dump includes | Daily | 90 days | NAS |

### PostgreSQL restore procedure

```bash
# 1. Stop services that write to Postgres
docker compose stop orchestrator control-api event-ingest

# 2. Restore from backup
BACKUP_FILE="backup_2026-03-19_020000.pgdump"
docker compose -f infra/docker/compose.infra.yml exec -T postgres \
  pg_restore -U computer -d computer_production \
  --clean --if-exists < /mnt/nas/backups/postgres/${BACKUP_FILE}

# 3. Verify record count (spot check)
docker compose -f infra/docker/compose.infra.yml exec -T postgres \
  psql -U computer -c "SELECT COUNT(*) FROM jobs;"

# 4. Run migrations to latest (in case restore was to older schema)
uv run --project apps/digital-twin alembic upgrade head
uv run --project apps/orchestrator alembic upgrade head

# 5. Restart services
docker compose -f infra/docker/compose.kernel.yml up -d
docker compose -f infra/docker/compose.api.yml up -d

# 6. Verify health
./bootstrap.sh --health-check
```

### Backup restore drill

Restore drills must be performed:
- Before any `field-qualified` release
- Monthly (automated or manual)
- After any significant infrastructure change

Drill procedure:
1. Restore latest daily backup to a staging environment.
2. Run smoke tests against staging.
3. Record: date, backup file used, restore time, smoke test result.
4. Log in `docs/runbooks/backup-restore-log.md`.

A field-qualified release is not permitted if the last backup restore drill was more than 30 days ago.

## Data loss scenarios

| Scenario | Recovery | RPO | RTO |
|---------|---------|-----|-----|
| Single service crash | Restart (systemd / Docker restart policy) | 0 (in-memory state only) | < 1 min |
| Postgres crash (no data loss) | Restart Postgres; services resume | 0 | < 5 min |
| Postgres data corruption | Restore from last WAL or daily dump | < 24h (dump) or < 1h (WAL) | < 60 min |
| Host OS failure | Restore from NAS backup to new host | < 24h | < 4 hours |
| Total site loss | Restore from off-site backup | < 24h | < 8 hours |

These are targets, not guarantees. Regular drills validate actual RTO/RPO.
