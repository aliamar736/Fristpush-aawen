#!/usr/bin/env bash
# AAWEN — one-command DEMO / STAGING server on a fresh Ubuntu 24.04 machine.
#
#   curl -fsSL https://raw.githubusercontent.com/aliamar736/Fristpush-aawen/main/scripts/install-server.sh \
#     | sudo bash -s -- --domain demo.example.ly
#
# Without --domain the site is served over plain HTTP on the server's IP (the phone's "use my location"
# button needs HTTPS, so a domain is recommended). Re-running the script updates the code and restarts.
#
# What this server is: demo data marked «تجريبي», login codes shown on screen (simulated SMS),
# simulated payments. It is NOT the production setup — see docs/OPERATIONS.md §4 for that.
set -euo pipefail

DOMAIN=""
REPO="https://github.com/aliamar736/Fristpush-aawen.git"
BRANCH="main"
APP_DIR="/opt/aawen"
DB_NAME="aawen"
DB_USER="aawen"
NO_SYSTEMD=0          # for testing inside containers: start processes directly
SKIP_APT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dir) APP_DIR="$2"; shift 2 ;;
    --db) DB_NAME="$2"; DB_USER="$2"; shift 2 ;;
    --no-systemd) NO_SYSTEMD=1; shift ;;
    --skip-apt) SKIP_APT=1; shift ;;
    *) echo "unknown option $1"; exit 1 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)."; exit 1; }
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ENV_DIR=/etc/aawen
ENV_FILE="$ENV_DIR/backend.env"

# ---------------------------------------------------------------- packages
if [ "$SKIP_APT" = 0 ]; then
  step "Installing system packages (PostgreSQL + PostGIS, Redis, Caddy, Python, GDAL)"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q git curl ca-certificates python3-venv python3-dev build-essential libpq-dev \
    gdal-bin libgdal-dev libgeos-dev libproj-dev postgresql postgresql-16-postgis-3 redis-server caddy
  if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
    step "Installing Node.js 22 (needed to build the web app)"
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -q nodejs
  fi
fi

# ---------------------------------------------------------------- code
step "Getting the code into $APP_DIR"
id aawen >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/aawen --shell /usr/sbin/nologin aawen
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$BRANCH" && git -C "$APP_DIR" checkout -q "$BRANCH" && git -C "$APP_DIR" reset -q --hard "origin/$BRANCH"
else
  git clone -q --depth 1 --branch "$BRANCH" "$REPO" "$APP_DIR"
fi

# ---------------------------------------------------------------- database
step "Database (PostgreSQL + PostGIS)"
pg_isready -q || { service postgresql start || true; sleep 3; }
mkdir -p "$ENV_DIR" && chmod 750 "$ENV_DIR"
if [ -f "$ENV_FILE" ]; then
  DB_PASS="$(sed -n 's#^DATABASE_URL=postgis://[^:]*:\([^@]*\)@.*#\1#p' "$ENV_FILE")"
else
  DB_PASS="$(openssl rand -hex 24)"
fi
sudo -u postgres psql -q -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';
  ELSE ALTER ROLE $DB_USER PASSWORD '$DB_PASS'; END IF;
END \$\$;
SQL
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
sudo -u postgres psql -q -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
pg_isready -q && (redis-cli ping >/dev/null 2>&1 || service redis-server start || true)

# ---------------------------------------------------------------- configuration
IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
HOST="${DOMAIN:-$IP}"
SCHEME=$([ -n "$DOMAIN" ] && echo https || echo http)
if [ ! -f "$ENV_FILE" ]; then
  step "Writing configuration to $ENV_FILE"
  cat > "$ENV_FILE" <<ENV
# AAWEN demo/staging server. Demo data, simulated SMS (code shown on screen), simulated payments.
AAWEN_ENV=development
DEBUG=false
SECRET_KEY=$(openssl rand -hex 40)
DATABASE_URL=postgis://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://localhost:6379/0
CACHE_URL=redis://localhost:6379/1
ALLOWED_HOSTS=$HOST,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=$SCHEME://$HOST
CORS_ALLOWED_ORIGINS=$SCHEME://$HOST
PUBLIC_WEB_URL=$SCHEME://$HOST
MEDIA_ROOT=/var/lib/aawen/media
SMS_PROVIDER=console
PUSH_PROVIDER=simulated
AI_PROVIDER=local
PAYMENTS_MODE=simulated
PAYMENT_PROVIDER=simulator
DEMO_DATA_ALLOWED=true
THROTTLE_OTP=60/hour
THROTTLE_LOGIN=60/hour
ENV
fi
chgrp aawen "$ENV_DIR" "$ENV_FILE" && chmod 750 "$ENV_DIR" && chmod 640 "$ENV_FILE"   # the app user must be able to read it
ln -sf "$ENV_FILE" "$APP_DIR/backend/.env"
mkdir -p /var/lib/aawen/media && chown -R aawen:aawen /var/lib/aawen

# ---------------------------------------------------------------- backend
step "Backend (Python packages, tables, demo data)"
cd "$APP_DIR/backend"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed_reference
if ! .venv/bin/python manage.py shell -c "from apps.accounts.models import User; import sys; sys.exit(0 if User.objects.filter(is_demo=True).exists() else 1)"; then
  .venv/bin/python manage.py seed_demo
fi
.venv/bin/python manage.py collectstatic --noinput -v 0
# files created above by root (demo photos, logs) must belong to the app user
chown -R aawen:aawen /var/lib/aawen
mkdir -p "$APP_DIR/backend/var" && chown -R aawen:aawen "$APP_DIR/backend/var"

# ---------------------------------------------------------------- web
step "Web app (build)"
cd "$APP_DIR/web"
npm ci --no-audit --no-fund --loglevel=error
npm run build --silent
chmod -R o+rX "$APP_DIR/web/dist" "$APP_DIR/backend/staticfiles"

# ---------------------------------------------------------------- web server
step "Web server (Caddy${DOMAIN:+, automatic HTTPS for $DOMAIN})"
cat > /etc/caddy/Caddyfile <<CADDY
${DOMAIN:-:80} {
	encode gzip
	request_body {
		max_size 12MB
	}
	header {
		X-Content-Type-Options nosniff
		Referrer-Policy same-origin
	}
	handle /api/* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /django-admin/* {
		reverse_proxy 127.0.0.1:8000
	}
	handle_path /static/* {
		root * $APP_DIR/backend/staticfiles
		file_server
	}
	handle {
		root * $APP_DIR/web/dist
		try_files {path} /index.html
		file_server
	}
}
CADDY

# ---------------------------------------------------------------- services
step "Starting services"
GUNICORN="$APP_DIR/backend/.venv/bin/gunicorn config.wsgi:application -b 127.0.0.1:8000 -w 3 --timeout 60"
CELERY="$APP_DIR/backend/.venv/bin/celery -A config worker -B -l info --concurrency 2"
if [ "$NO_SYSTEMD" = 1 ]; then
  cd "$APP_DIR/backend"
  pkill -f "gunicorn config.wsgi" 2>/dev/null || true
  setsid nohup sudo -u aawen $GUNICORN > /tmp/aawen-api.log 2>&1 < /dev/null &
  setsid nohup sudo -u aawen $CELERY > /tmp/aawen-worker.log 2>&1 < /dev/null &
  caddy validate --config /etc/caddy/Caddyfile >/dev/null
  (caddy stop >/dev/null 2>&1 || true); setsid nohup caddy run --config /etc/caddy/Caddyfile > /tmp/aawen-caddy.log 2>&1 < /dev/null &
else
  cat > /etc/systemd/system/aawen-api.service <<UNIT
[Unit]
Description=AAWEN API (gunicorn)
After=network.target postgresql.service redis-server.service
[Service]
User=aawen
WorkingDirectory=$APP_DIR/backend
ExecStart=$GUNICORN
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  cat > /etc/systemd/system/aawen-worker.service <<UNIT
[Unit]
Description=AAWEN background worker (celery + beat)
After=network.target postgresql.service redis-server.service
[Service]
User=aawen
WorkingDirectory=$APP_DIR/backend
ExecStart=$CELERY
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable -q --now postgresql redis-server
  systemctl enable -q aawen-api aawen-worker caddy
  systemctl restart aawen-api aawen-worker caddy
  if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80/tcp; ufw allow 443/tcp; fi
fi

# ---------------------------------------------------------------- check
step "Checking"
for i in $(seq 1 30); do
  curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8000/api/v1/health && echo

cat <<DONE

  AAWEN is running:  $SCHEME://$HOST
  API documentation: $SCHEME://$HOST/api/v1/docs

  Demo logins (type the number; the login code appears on the screen):
    0910000012 citizen          0910000002 reviewer       0910000003 coordinator
    0910000004 cleaning agency  0910000014 field worker   0910000010 accountant
    0910000011 auditor          0910000001 system admin

  This is a DEMO server (demo data, simulated SMS and payments). Do not put real reports on it.
  Update later by running the same command again.
DONE
