#!/usr/bin/env bash
# One-command demo launcher for Autonomous SQL Agent.
# - Verifies env, venv, deps
# - Seeds SQLite demo DB if missing
# - Starts API + frontend
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
API_HOST="${API_HOST:-127.0.0.1}"
API_BASE_URL="${API_BASE_URL:-http://localhost:$API_PORT}"
FRONTEND_CONFIG="$ROOT_DIR/frontend/config.js"
API_LOG="$ROOT_DIR/.api-demo.log"

kill_port() {
  local port="$1"
  local pids pid command
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"

  if [ -n "$pids" ]; then
    echo "==> Freeing port $port (PID $pids)"
    kill $pids 2>/dev/null || true
    sleep 1
  fi

  for pid in $(lsof -ti:"$port" 2>/dev/null || true); do
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    case "$command" in
      *"uvicorn api.main:app"*|*"http.server $port"*|*"$ROOT_DIR"*)
        echo "==> Stopping stale demo process on port $port (PID $pid)"
        kill "$pid" 2>/dev/null || true
        ;;
    esac
  done
  sleep 1

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "==> Force-freeing port $port (PID $pids)"
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
}

wait_for_api() {
  local url="$1"
  for _ in $(seq 1 30); do
    if curl -fsS -m 2 "$url/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cleanup() {
  echo ""
  echo "Shutting down..."
  kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true
  exit 0
}

if [ ! -f .env ]; then
  echo "ERROR: .env not found."
  echo "  cp .env.example .env  # then add your GROQ_API_KEY"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating venv..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip --quiet
fi

echo "==> Installing Python dependencies..."
.venv/bin/pip install -r requirements.txt --quiet

if [ ! -f data/demo.sqlite ]; then
  echo "==> Seeding SQLite demo DB..."
  .venv/bin/python scripts/seed_sqlite_demo.py
fi

kill_port "$API_PORT"
kill_port "$WEB_PORT"

cat > "$FRONTEND_CONFIG" <<EOF
window.APP_CONFIG = {
  API_BASE: "$API_BASE_URL"
};
EOF

echo "==> Starting API on $API_BASE_URL ..."
.venv/bin/uvicorn api.main:app --host "$API_HOST" --port "$API_PORT" --log-level info > "$API_LOG" 2>&1 &
API_PID=$!

trap cleanup INT TERM

if ! wait_for_api "$API_BASE_URL"; then
  echo "ERROR: API did not become healthy."
  echo "Last API log lines:"
  tail -40 "$API_LOG" || true
  kill "$API_PID" 2>/dev/null || true
  exit 1
fi

# Auto-onboard the demo dataset if not already onboarded
DATASETS=$(curl -s -m 5 "$API_BASE_URL/dataset/list" 2>/dev/null || echo "")
if [ -n "$DATASETS" ] && ! echo "$DATASETS" | grep -q "demo_sales"; then
  echo "==> Onboarding demo SQLite dataset..."
  curl -s -X POST "$API_BASE_URL/dataset/onboard" \
    -H "Content-Type: application/json" \
    -d '{"name":"demo_sales","db_engine":"sqlite","schema_name":"main","description":"Demo e-commerce SQLite","source_config":{"db_path":"data/demo.sqlite"}}' \
    > /dev/null
  echo "==> Demo dataset onboarded."
fi

echo ""
echo "============================================================"
echo " Frontend:   http://localhost:$WEB_PORT"
echo " API docs:   $API_BASE_URL/docs"
echo " Press Ctrl+C to stop both"
echo "============================================================"
echo ""

cd frontend
python3 -m http.server "$WEB_PORT" &
WEB_PID=$!
wait "$WEB_PID"
