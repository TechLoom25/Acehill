#!/usr/bin/env bash
# Push the current code to the server. Run from the project root on your own machine:
#     SERVER=youruser@DROPLET_IP ./deploy/deploy.sh
set -euo pipefail
: "${SERVER:?Set SERVER=user@host first}"
cd "$(dirname "$0")/.."

echo "==> Building frontend"
(cd frontend && npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund; npm run build)

echo "==> Uploading"
rsync -az --delete --exclude '.venv' --exclude '.env' --exclude '*.db' --exclude '.secret_key' \
      --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'tests' backend/ "$SERVER":acehill-upload/backend/
rsync -az --delete frontend/dist/ "$SERVER":acehill-upload/frontend/

echo "==> Installing on the server"
ssh -t "$SERVER" '
  set -e
  sudo rsync -a --delete --exclude .venv --exclude .env --exclude .secret_key ~/acehill-upload/backend/ /opt/acehill/backend/
  sudo rsync -a --delete ~/acehill-upload/frontend/ /var/www/acehill/frontend/
  sudo chown -R acehill:acehill /opt/acehill
  sudo -u acehill /opt/acehill/backend/.venv/bin/pip install -q -r /opt/acehill/backend/requirements.txt
  sudo systemctl restart acehill-backend
  sleep 2
  curl -fsS http://127.0.0.1:8010/health && echo
'
echo "==> Done"
