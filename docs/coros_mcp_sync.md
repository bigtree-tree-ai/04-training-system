# COROS MCP Daily Sync

## Commands

```bash
python -m training.cli coros-login
python -m training.cli coros-sync 14
python -m training.cli coros-overview
```

`coros-login` stores OAuth credentials in `.coros_auth.json`, which is ignored by Git. Daily jobs use the refresh token from that file and do not require repeated login.

## Dashboard Auth

Production deployment requires HTTP Basic auth for pages and APIs.

Create `/opt/training-system/.env` on the server:

```bash
TRAIN_AUTH_USER=your_user
TRAIN_AUTH_PASSWORD=your_long_random_password
```

The systemd service sets `TRAIN_AUTH_REQUIRED=1` and reads this file. If auth is required but the credentials are missing, private routes return HTTP 503 instead of serving personal training data publicly.

## Remote COROS OAuth

Do not run `coros-login` directly on a headless server unless you have a working browser and callback path. The default login flow opens a local browser and listens on `127.0.0.1`.

Recommended flow:

```bash
# On a trusted local machine
python -m training.cli coros-login

# Upload the generated credential file to the server
scp .coros_auth.json root@101.37.238.138:/opt/training-system/.coros_auth.json
ssh root@101.37.238.138 'chmod 600 /opt/training-system/.coros_auth.json'
```

Then run one manual sync on the server:

```bash
cd /opt/training-system
python3 -m training.cli coros-sync 14
python3 -m training.cli coros-overview
```

## Daily Cron

```cron
15 5 * * * cd /opt/training-system && /usr/bin/python3 -m training.cli coros-sync 14 >> logs/coros-sync.log 2>&1
```

The sync writes structured data into these groups:

- Training: fitness assessment, training load, upcoming schedule.
- Daily life: steps, calories, non-workout activity, stress summary.
- Health recovery: recovery percentage, sleep, HRV, resting heart rate, average heart rate.
- Planning and devices: user profile, bound COROS devices, sync runs.
