#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Deploy script for sku-ops on a VPS (Hetzner / DigitalOcean / etc).
#
# Handles:
#   1. Env validation
#   2. Frontend build (npm ci + vite build)
#   3. Nginx config rendering (substitutes __DOMAIN__ placeholder)
#   4. First-time TLS provisioning via Certbot
#   5. Docker image build + rolling restart
#
# Usage:
#   ./deploy/scripts/deploy.sh              # Full deploy
#   ./deploy/scripts/deploy.sh --skip-build # Skip frontend build (e.g., CI already built it)
#   ./deploy/scripts/deploy.sh --init-tls   # Only provision TLS certs (first-time setup)
#
# Prerequisites:
#   - .env file with all required variables (copy from .env.production.example)
#   - Docker + Docker Compose installed
#   - Node.js + npm installed (for frontend build, or skip with --skip-build)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# ── Flags ────────────────────────────────────────────────────────────────────
SKIP_BUILD=false
INIT_TLS_ONLY=false

for arg in "$@"; do
  case $arg in
    --skip-build) SKIP_BUILD=true ;;
    --init-tls)   INIT_TLS_ONLY=true ;;
  esac
done

# ── Load & validate .env ────────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "ERROR: .env file not found. Copy .env.production.example to .env and fill in required values."
  exit 1
fi

set -a; source .env; set +a

REQUIRED_VARS=(DOMAIN POSTGRES_PASSWORD JWT_SECRET CORS_ORIGINS)
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    MISSING+=("$var")
  fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
  echo "ERROR: Missing required environment variables: ${MISSING[*]}"
  echo "       See .env.production.example for documentation."
  exit 1
fi

# Frontend vars are baked into the JS bundle at build time.
# Without these, the frontend falls back to bridge auth (broken in production).
FRONTEND_VARS=(VITE_SUPABASE_URL VITE_SUPABASE_ANON_KEY)
FE_MISSING=()
for var in "${FRONTEND_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    FE_MISSING+=("$var")
  fi
done
if [ ${#FE_MISSING[@]} -gt 0 ]; then
  echo "ERROR: Missing frontend build variables: ${FE_MISSING[*]}"
  echo "       These are baked into the JS at build time (cannot be changed after deploy)."
  echo "       Get them from Supabase Dashboard > Settings > API."
  exit 1
fi

echo "=== Deploying sku-ops to ${DOMAIN} ==="
echo ""

# ── Render nginx config ─────────────────────────────────────────────────────
echo "[1/5] Rendering nginx config for ${DOMAIN}..."
sed "s/__DOMAIN__/${DOMAIN}/g" deploy/nginx/nginx.conf > deploy/nginx/nginx.rendered.conf

# ── TLS provisioning ────────────────────────────────────────────────────────
DC="docker compose -f docker-compose.yml"

init_tls() {
  echo "[2/5] Provisioning TLS certificate for ${DOMAIN}..."

  # Start nginx with a temporary self-signed cert to handle ACME challenge
  mkdir -p deploy/nginx/ssl-temp
  if [ ! -f deploy/nginx/ssl-temp/fullchain.pem ]; then
    openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
      -keyout deploy/nginx/ssl-temp/privkey.pem \
      -out deploy/nginx/ssl-temp/fullchain.pem \
      -subj "/CN=${DOMAIN}" 2>/dev/null
  fi

  # Use temp config that serves ACME challenge on port 80 only
  cat > deploy/nginx/nginx.init-tls.conf <<'INITCONF'
worker_processes 1;
events { worker_connections 128; }
http {
    server {
        listen 80;
        server_name _;
        location /.well-known/acme-challenge/ { root /var/www/certbot; }
        location / { return 503; }
    }
}
INITCONF

  # Start nginx with init config
  $DC run -d --rm \
    -v "$(pwd)/deploy/nginx/nginx.init-tls.conf:/etc/nginx/nginx.conf:ro" \
    --name sku-ops-nginx-init \
    -p 80:80 \
    nginx || true

  sleep 2

  $DC run --rm certbot certbot certonly \
    --webroot -w /var/www/certbot \
    -d "${DOMAIN}" \
    --email "${CERTBOT_EMAIL:-admin@${DOMAIN}}" \
    --agree-tos \
    --non-interactive

  # Stop the temp nginx
  docker stop sku-ops-nginx-init 2>/dev/null || true
  rm -rf deploy/nginx/ssl-temp deploy/nginx/nginx.init-tls.conf

  echo "    TLS certificate provisioned successfully."
}

if [ "$INIT_TLS_ONLY" = true ]; then
  init_tls
  echo "Done. Run ./deploy/scripts/deploy.sh to complete deployment."
  exit 0
fi

# Check if certs exist; if not, provision them
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
if ! $DC run --rm certbot test -f "${CERT_DIR}/fullchain.pem" 2>/dev/null; then
  init_tls
else
  echo "[2/5] TLS certificate found, skipping provisioning."
fi

# ── Frontend build ───────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = true ]; then
  echo "[3/5] Skipping frontend build (--skip-build)."
else
  echo "[3/5] Building frontend..."
  (cd frontend && npm ci && npm run build)
  echo "    Frontend built to frontend/dist/"
fi

# ── Docker build + restart ───────────────────────────────────────────────────
echo "[4/5] Building backend image..."
$DC build backend

echo "[5/5] Starting services..."
$DC up -d --force-recreate

echo ""
echo "Waiting for services to become healthy..."
sleep 5

BACKEND_HEALTH=$($DC exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').status)" 2>/dev/null || echo "unhealthy")
DB_HEALTH=$($DC exec db pg_isready -U sku_ops 2>/dev/null && echo "healthy" || echo "unhealthy")

echo ""
echo "=== Deployment Complete ==="
echo "  Domain:   https://${DOMAIN}"
echo "  Backend:  ${BACKEND_HEALTH}"
echo "  Database: ${DB_HEALTH}"
echo ""
echo "Post-deploy checklist:"
echo "  [ ] Verify https://${DOMAIN} loads the frontend"
echo "  [ ] Verify https://${DOMAIN}/api/health returns OK"
echo "  [ ] Set up backup cron: 0 3 * * * $(pwd)/deploy/scripts/backup-postgres.sh"
echo "  [ ] Configure firewall: allow 80, 443; block all else"
echo "  [ ] Set up monitoring/alerting for the health endpoint"
