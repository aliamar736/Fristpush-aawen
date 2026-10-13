#!/usr/bin/env bash
# Starts API (relaxed throttles for automated runs) + built web preview, then runs Playwright E2E.
set -euo pipefail
cd "$(dirname "$0")/.."
( cd backend && . .venv/bin/activate && python manage.py seed_demo >/dev/null && \
  THROTTLE_OTP=10000/hour THROTTLE_LOGIN=10000/hour THROTTLE_REPORT=10000/hour THROTTLE_UPLOAD=10000/hour \
  python manage.py runserver 127.0.0.1:8000 ) & API=$!
( cd web && npm run build >/dev/null && npx vite preview --port 4173 --host 127.0.0.1 ) & WEB=$!
trap 'kill $API $WEB 2>/dev/null' EXIT
sleep 8
( cd web && npx playwright test )
