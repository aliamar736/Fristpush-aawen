#!/usr/bin/env bash
# Runs every automated test suite and writes results to docs/test-results/.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/test-results
( cd backend && . .venv/bin/activate && AAWEN_ENV=test python -m pytest --create-db --cov=apps --cov-report=term \
    --junitxml=../docs/test-results/backend-junit.xml ) | tee docs/test-results/backend.txt
( cd web && npx tsc -b && npx vitest run ) 2>&1 | tee docs/test-results/web-unit.txt
( cd web && PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH:-} npx playwright test --reporter=list ) 2>&1 | tee docs/test-results/web-e2e.txt
