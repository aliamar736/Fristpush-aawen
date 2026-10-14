#!/usr/bin/env bash
# Runs every time the codespace starts: API, background worker, and the web app.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG=/tmp/aawen
mkdir -p "$LOG"

cd "$ROOT/backend"
. .venv/bin/activate
setsid nohup python manage.py runserver 0.0.0.0:8000 > "$LOG/api.log" 2>&1 < /dev/null &
setsid nohup celery -A config worker -B -l info > "$LOG/worker.log" 2>&1 < /dev/null &

cd "$ROOT/web"
setsid nohup npm run dev -- --host 0.0.0.0 > "$LOG/web.log" 2>&1 < /dev/null &

echo "AAWEN is starting. Open the PORTS tab and click the globe next to 'AAWEN app' (5173)."
echo "Logs: $LOG/api.log  $LOG/web.log  $LOG/worker.log"
