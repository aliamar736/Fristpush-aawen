#!/usr/bin/env bash
# One-time setup when the codespace is created: dependencies, database, demo data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend dependencies"
cd "$ROOT/backend"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements-dev.txt -q

if [ ! -f .env ]; then
  WEB_URL="http://localhost:5173"
  if [ -n "${CODESPACE_NAME:-}" ]; then
    WEB_URL="https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  fi
  cat > .env <<ENV
AAWEN_ENV=development
DEBUG=true
DATABASE_URL=postgis://aawen:devpass@localhost:5432/aawen
REDIS_URL=redis://redis:6379/0
CACHE_URL=redis://redis:6379/1
ALLOWED_HOSTS=localhost,127.0.0.1,.app.github.dev,.preview.app.github.dev
CSRF_TRUSTED_ORIGINS=https://*.app.github.dev
CORS_ALLOWED_ORIGINS=http://localhost:5173
PUBLIC_WEB_URL=${WEB_URL}
SMS_PROVIDER=console
PUSH_PROVIDER=simulated
AI_PROVIDER=local
PAYMENTS_MODE=simulated
PAYMENT_PROVIDER=simulator
DEMO_DATA_ALLOWED=true
THROTTLE_OTP=200/hour
THROTTLE_LOGIN=200/hour
THROTTLE_REPORT=300/hour
THROTTLE_UPLOAD=600/hour
THROTTLE_ROAD=300/hour
ENV
fi

echo "==> Waiting for the database"
for i in $(seq 1 60); do
  pg_isready -h localhost -U aawen -q && break
  sleep 2
done
psql "postgresql://aawen:devpass@localhost:5432/aawen" -q \
  -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo "==> Database tables and demo data (marked تجريبي)"
python manage.py migrate --noinput
python manage.py seed_reference
python manage.py seed_demo

echo "==> Web dependencies"
cd "$ROOT/web"
npm ci --no-audit --no-fund

echo "==> Setup finished"
