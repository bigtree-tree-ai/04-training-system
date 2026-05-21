#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${TRAIN_SERVER_HOST:-101.37.238.138}"
SERVER_USER="${TRAIN_SERVER_USER:-root}"
SERVER_PORT="${TRAIN_SERVER_PORT:-22}"
SERVER_PASS="${TRAIN_SERVER_PASS:-}"
DEPLOY_DIR="${TRAIN_DEPLOY_DIR:-/opt/training-system}"
REPO_URL="${TRAIN_REPO_URL:-https://github.com/bigtree-tree-ai/training-system.git}"
SERVICE_NAME="${TRAIN_SERVICE_NAME:-training-web}"
WEB_PORT="${TRAIN_WEB_PORT:-8082}"
ROOT_PATH="${ROOT_PATH:-/training}"
AUTH_USER="${TRAIN_AUTH_USER:-}"
AUTH_PASSWORD="${TRAIN_AUTH_PASSWORD:-}"

SSH_BASE=(-p "$SERVER_PORT" -o StrictHostKeyChecking=no -o ConnectTimeout=10)
if [[ -n "$SERVER_PASS" ]] && command -v sshpass >/dev/null 2>&1; then
  SSH=(sshpass -p "$SERVER_PASS" ssh "${SSH_BASE[@]}" -o PubkeyAuthentication=no "${SERVER_USER}@${SERVER_HOST}")
else
  SSH=(ssh "${SSH_BASE[@]}" -o BatchMode=yes "${SERVER_USER}@${SERVER_HOST}")
fi

echo "== Training System Aliyun deploy =="
echo "Target: ${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}"

"${SSH[@]}" "bash -s" <<ENDSSH
set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  apt-get update && apt-get install -y git
fi
if ! command -v python3 >/dev/null 2>&1; then
  apt-get update && apt-get install -y python3 python3-pip
fi

if [ -d "${DEPLOY_DIR}/.git" ]; then
  cd "${DEPLOY_DIR}"
  git fetch origin main
  git reset --hard origin/main
else
  mkdir -p "$(dirname "${DEPLOY_DIR}")"
  git clone "${REPO_URL}" "${DEPLOY_DIR}"
  cd "${DEPLOY_DIR}"
fi

python3 -m pip install -r requirements.txt
python3 -m training.cli coros-overview >/dev/null

if [ ! -f "${DEPLOY_DIR}/.env" ]; then
  if [ -n "${AUTH_USER}" ] && [ -n "${AUTH_PASSWORD}" ]; then
    umask 077
    cat > "${DEPLOY_DIR}/.env" <<'ENV'
TRAIN_AUTH_USER=${AUTH_USER}
TRAIN_AUTH_PASSWORD=${AUTH_PASSWORD}
ENV
  else
    cat >&2 <<'MSG'
Missing dashboard auth config.
Create /opt/training-system/.env with TRAIN_AUTH_USER and TRAIN_AUTH_PASSWORD,
or rerun deploy with TRAIN_AUTH_USER=... TRAIN_AUTH_PASSWORD=...
MSG
    exit 1
  fi
else
  chmod 600 "${DEPLOY_DIR}/.env"
fi

if ! grep -q '^TRAIN_AUTH_USER=' "${DEPLOY_DIR}/.env" || ! grep -q '^TRAIN_AUTH_PASSWORD=' "${DEPLOY_DIR}/.env"; then
  cat >&2 <<'MSG'
/opt/training-system/.env exists but does not contain both TRAIN_AUTH_USER and TRAIN_AUTH_PASSWORD.
MSG
  exit 1
fi

cat > /etc/systemd/system/${SERVICE_NAME}.service <<'SERVICE'
[Unit]
Description=Training Analysis System
After=network.target

[Service]
Type=simple
WorkingDirectory=${DEPLOY_DIR}
Environment=TRAIN_WEB_HOST=0.0.0.0
Environment=TRAIN_WEB_PORT=${WEB_PORT}
Environment=ROOT_PATH=${ROOT_PATH}
Environment=TRAIN_AUTH_REQUIRED=1
EnvironmentFile=-${DEPLOY_DIR}/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 -m uvicorn training.web.app:app --host 0.0.0.0 --port ${WEB_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

mkdir -p "${DEPLOY_DIR}/logs"
CRON_CMD="cd ${DEPLOY_DIR} && /usr/bin/python3 -m training.cli coros-sync 14 >> ${DEPLOY_DIR}/logs/coros-sync.log 2>&1"
(crontab -l 2>/dev/null | grep -v "training.cli coros-sync" || true; echo "15 5 * * * \$CRON_CMD") | crontab -

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
systemctl --no-pager --full status ${SERVICE_NAME} | head -40
ENDSSH

echo "Deploy command completed."
echo "Verify: http://${SERVER_HOST}/training or http://${SERVER_HOST}:${WEB_PORT}/coros"
