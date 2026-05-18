# Progress: COROS MCP Sync + Aliyun Deploy

Date: 2026-05-18
Project: `06-运动数据AI化/training-system`
Branch: `main`

## Current Status

Implemented and pushed to GitHub.

Latest commits:

- `71264f4 fix: fail fast without Aliyun ssh password`
- `9b9c520 chore: add Aliyun deploy script`
- `f75b4a8 feat: add COROS MCP daily sync`

GitHub remote:

- `https://github.com/bigtree-tree-ai/training-system.git`

## Completed Work

COROS MCP integration:

- Added browser OAuth login command: `python -m training.cli coros-login`
- Added daily sync command: `python -m training.cli coros-sync 14`
- Added overview command: `python -m training.cli coros-overview`
- Added token refresh support via local `.coros_auth.json`
- `.coros_auth.json` is ignored by Git.

Structured storage:

- `coros_profile`
- `coros_devices`
- `coros_recovery_snapshots`
- `coros_fitness_snapshots`
- `coros_training_load`
- `coros_daily_health`
- `coros_sleep`
- `coros_hrv`
- `coros_heart_rate_daily`
- `coros_stress_daily`
- `coros_training_schedule`
- `coros_sport_records`
- `coros_sync_runs`

Web/API:

- New page: `/coros`
- New API: `/api/coros/overview`
- New protected sync API: `/api/coros/sync`
- Dashboard pipeline now attempts COROS sync before FIT import/analysis.

Deployment assets:

- `scripts/deploy_aliyun.sh`
- `deploy/training-system.service`
- `docs/coros_mcp_sync.md`

## Validation Completed

Local tests:

```bash
/opt/homebrew/bin/python3.14 -m pytest
```

Result:

```text
81 passed
```

Syntax checks:

```bash
bash -n scripts/deploy_aliyun.sh
/opt/homebrew/bin/python3.14 -m compileall training
```

Result: passed.

Local web validation:

- `/coros` returned HTTP 200.
- `/api/coros/overview` returned structured sections:
  - `training`
  - `daily_life`
  - `health_recovery`
  - `planning_devices`

Local baseline data was seeded into local `training.db` from the COROS MCP readings gathered during development. This DB is ignored by Git and is not deployed.

## Current Blocker

Aliyun deployment is blocked by SSH authentication.

Command attempted:

```bash
bash scripts/deploy_aliyun.sh
```

Result:

```text
root@101.37.238.138: Permission denied (publickey,password).
```

Direct SSH check also failed:

```text
root@101.37.238.138: Permission denied (publickey,password).
```

The server is reachable, but this machine's current SSH key is not accepted for `root@101.37.238.138`.

## Next Steps

1. Fix server authentication using one of these:

```bash
# Option A: add this machine's public key to root's authorized_keys on Aliyun
cat ~/.ssh/id_ed25519.pub
```

or:

```bash
# Option B: run deploy with password
TRAIN_SERVER_PASS='SERVER_PASSWORD' bash scripts/deploy_aliyun.sh
```

2. After deploy succeeds, complete one-time COROS auth on the server:

```bash
cd /opt/training-system
python3 -m training.cli coros-login
```

This creates `/opt/training-system/.coros_auth.json` on the server for refresh-token based daily sync.

3. Run one manual server sync:

```bash
cd /opt/training-system
python3 -m training.cli coros-sync 14
python3 -m training.cli coros-overview
```

4. Verify service:

```bash
systemctl status training-system
curl -I http://101.37.238.138:8082/coros
```

If Nginx reverse proxy is configured for `/training`, also verify:

```bash
curl -I http://101.37.238.138/training/coros
```

5. Confirm cron exists:

```bash
crontab -l | grep "training.cli coros-sync"
```

Expected daily job:

```cron
15 5 * * * cd /opt/training-system && /usr/bin/python3 -m training.cli coros-sync 14 >> /opt/training-system/logs/coros-sync.log 2>&1
```
