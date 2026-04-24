#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/stock-analyzer}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ROLLBACK_STATE_FILE="${ROLLBACK_STATE_FILE:-.deploy-last-success.env}"

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "[deploy] missing required variable: ${name}" >&2
    exit 1
  fi
}

require_var GHCR_USERNAME
require_var GHCR_TOKEN
require_var API_IMAGE
require_var FRONTEND_IMAGE

cd "$APP_DIR"

if [ ! -f .env ]; then
  echo "[deploy] missing .env in $APP_DIR" >&2
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy] missing $COMPOSE_FILE in $APP_DIR" >&2
  exit 1
fi

PREVIOUS_API_IMAGE=""
PREVIOUS_FRONTEND_IMAGE=""

if docker ps -a --format '{{.Names}}' | grep -q '^stock-api$'; then
  PREVIOUS_API_IMAGE="$(docker inspect stock-api --format '{{.Config.Image}}')"
fi

if docker ps -a --format '{{.Names}}' | grep -q '^stock-frontend$'; then
  PREVIOUS_FRONTEND_IMAGE="$(docker inspect stock-frontend --format '{{.Config.Image}}')"
fi

rollback() {
  local exit_code="$1"
  if [ "$exit_code" -eq 0 ]; then
    return
  fi

  echo "[deploy] deploy failed, attempting rollback" >&2
  if [ -n "$PREVIOUS_API_IMAGE" ] && [ -n "$PREVIOUS_FRONTEND_IMAGE" ]; then
    export API_IMAGE="$PREVIOUS_API_IMAGE"
    export FRONTEND_IMAGE="$PREVIOUS_FRONTEND_IMAGE"
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans || true
  fi
}

trap 'rollback $?' EXIT

printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

export API_IMAGE
export FRONTEND_IMAGE

docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --wait
docker compose -f "$COMPOSE_FILE" exec -T stock-api sh -lc 'cd /app && PYTHONPATH=/app python -m alembic upgrade head'
docker exec stock-api curl -fsS http://localhost:8000/health >/dev/null

cat > "$ROLLBACK_STATE_FILE" <<EOF
API_IMAGE=${API_IMAGE}
FRONTEND_IMAGE=${FRONTEND_IMAGE}
DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "[deploy] deployment completed successfully"
