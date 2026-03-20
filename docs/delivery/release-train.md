# Release Train

Defines the release cadence, branching strategy, and window management.

## Release cadence

| Component class | Cadence | Branch strategy |
|----------------|---------|----------------|
| Web/backend services | Weekly (as needed) | main → release branch → tag |
| Control services | Monthly | main → release branch → tag |
| Robotics | Compatibility sprint only | feature branch → main → tag after SITL |
| HA/Frigate adapters | Monthly (aligned with upstream) | main → release branch → tag |
| Model runtimes | Quarterly | main → release branch → tag |

## Branching model

```
main                    ← always deployable (all CI gates pass)
  ├── feature/...       ← feature branches; PRs to main
  ├── release/site-stable/v1.2.0  ← release branch; fixes only
  └── hotfix/...        ← emergency fixes; PR to main + release branch
```

No long-lived feature branches. Features merge to main when CI passes. Release branches are cut from main when deploying.

## Release process

### Step 1: Cut release branch

```bash
git checkout main
git pull origin main
git checkout -b release/site-stable/orchestrator/v1.2.0
```

### Step 2: Update versions

```bash
# Update CHANGELOG.md in the affected service
# Update version in pyproject.toml or package.json
# Commit changes to release branch
```

### Step 3: Full CI run

Push release branch. All applicable CI lanes must pass on the release branch.

### Step 4: Create release

```bash
git tag site-stable/orchestrator/v1.2.0
git push origin site-stable/orchestrator/v1.2.0
```

The release workflow runs, builds Docker images, and creates a GitHub Release.

### Step 5: Verify backup

Before deploying to production: run backup verification job. Record `backup-verified: true` in release notes.

### Step 6: Deploy

```bash
# On production host (via Ansible or manual)
ansible-playbook infra/ansible/deploy.yml \
  -e service=orchestrator \
  -e version=v1.2.0 \
  -e release_class=site-stable
```

Deploy script:
1. Pulls new Docker image
2. Runs pre-deploy health check
3. Performs rolling restart (zero-downtime if possible)
4. Runs post-deploy health check
5. On failure: automatic rollback to previous image

### Step 7: Post-deploy verification

Run smoke tests after deploy:
```bash
./tests/smoke/run_smoke.sh --env=production
```

### Step 8: Record

Update `RELEASES.md` with deploy date, version, operator who deployed, and verification result.

## Hotfix process

For urgent production fixes:

```bash
git checkout -b hotfix/fix-irrigation-state-machine main
# make fix
git commit -m "fix: correct irrigation state machine transition on valve-ack timeout"
# PR to main; must pass all CI gates
# If approved: also cherry-pick to current release branch
git tag site-stable/orchestrator/v1.2.1
```

Hotfixes follow the same CI gates as regular releases. No exceptions.

## Release window management

Production deployments:
- **Allowed window**: Monday–Thursday, 9am–4pm local time (avoid evenings, weekends, Fridays)
- **Forbidden**: During active site operations (active irrigation, active robot missions)
- **Robotics releases**: Require additional 24-hour notice to household

Control service releases (greenhouse-control, hydro-control):
- **Preferred**: Between crop cycles or during manual-operation windows
- **Required**: Notify ops-web and ensure no active jobs before deploy

## CHANGELOG format

Each service maintains a `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format:

```markdown
## [1.2.0] - 2026-03-19

### Added
- Job timeout configuration per risk_class

### Changed
- Improved retry logic for MQTT command dispatch

### Fixed
- State machine transition bug on valve-ack timeout

### rollback_to: 1.1.3
```

The `rollback_to` field is required. The release gate CI job checks for it.
