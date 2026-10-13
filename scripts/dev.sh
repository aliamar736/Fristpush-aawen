#!/usr/bin/env bash
# Local development without Docker: PostgreSQL+PostGIS and Redis must be running locally.
set -euo pipefail
cd "$(dirname "$0")/.."
( cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements-dev.txt \
  && python manage.py migrate && python manage.py seed_demo )
( cd web && npm ci )
echo "Start: (cd backend && . .venv/bin/activate && python manage.py runserver) & (cd backend && . .venv/bin/activate && celery -A config worker -B) & (cd web && npm run dev)"
