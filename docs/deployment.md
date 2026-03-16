# Deployment Guide (VPS / Self-Hosted)

> **This guide is for VPS self-hosted deployments only.**
> For the primary deployment path (Railway + Vercel + Supabase), see [DEPLOY.md](../DEPLOY.md).
> For per-client setup, see [docs/deploy-client.md](deploy-client.md).

## Branch Strategy

```
main        ← production (auto-deploys on push)
  ↑ PR
dev         ← integration branch (test before promoting to main)
  ↑ PR
feature/*   ← your working branches
```

**Daily workflow:**

1. Create a branch off `dev`: `git checkout -b feature/my-thing dev`
2. Push and open a PR targeting `dev`
3. CI runs automatically (backend lint + format + test, frontend lint + format + build + test, Docker build)
4. Merge to `dev` after review
5. When `dev` is stable, open a PR from `dev` -> `main`
6. Merging to `main` triggers auto-deploy to production and version bump (commitizen)

**CI/CD Workflows:**

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | Push/PR to main, dev | Backend: ruff lint + format check + pytest. Frontend: ESLint + Prettier check + build + vitest. Docker build. |
| `bump.yml` | Push to main | Auto-bumps version via commitizen, generates CHANGELOG, creates GitHub Release |
| `deploy.yml` | Push to main | SSH deploy to production VPS |

## GitHub Repository Setup

### Required Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `VPS_HOST` | Server IP or hostname |
| `VPS_USER` | SSH user (e.g., `deploy`) |
| `VPS_SSH_KEY` | Private SSH key for the deploy user |
| `VPS_SSH_PORT` | SSH port (typically `22`) |
| `VPS_APP_PATH` | Path to the repo on the server (e.g., `/opt/sku-ops`) |

### Recommended Branch Protection Rules

Go to **Settings → Branches → Add rule** for both `main` and `dev`:

**For `main`:**
- Require pull request before merging
- Require status checks to pass (select: `Backend`, `Frontend`, `Docker build`)
- Require branches to be up to date before merging
- Do not allow bypassing the above settings

**For `dev`:**
- Require pull request before merging
- Require status checks to pass (select: `Backend`, `Frontend`)

### Environment Protection

Go to **Settings → Environments → New environment** and create `production`:
- Add required reviewers (yourself)
- Restrict to `main` branch only

## First-Time Server Setup

### 1. Provision a VPS

Any Ubuntu 22.04+ VPS works (Hetzner, DigitalOcean, Linode). Minimum spec: 2 vCPU, 4 GB RAM.

### 2. Install dependencies

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Node.js (for frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# UFW firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

### 3. Clone and configure

```bash
sudo mkdir -p /opt/sku-ops
sudo chown $USER:$USER /opt/sku-ops
git clone https://github.com/stef-writes/sku-ops.git /opt/sku-ops
cd /opt/sku-ops
cp .env.production.example .env
```

Edit `.env` — fill in all `REQUIRED` values. At minimum:

```bash
DOMAIN=your-domain.com
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
CORS_ORIGINS=https://your-domain.com
```

### 4. Point DNS

Create an A record pointing `your-domain.com` to the server IP. Wait for propagation.

### 5. Deploy

```bash
./deploy/scripts/deploy.sh
```

This will:
1. Validate your `.env`
2. Render the nginx config with your domain
3. Provision a TLS certificate via Let's Encrypt
4. Build the frontend
5. Build the backend Docker image
6. Start the full stack

### 6. Set up backups

```bash
crontab -e
# Add:
0 3 * * * /opt/sku-ops/deploy/scripts/backup-postgres.sh >> /var/log/sku-ops-backup.log 2>&1
```

### 7. Verify

```bash
curl -s https://your-domain.com/api/health
# Should return {"status": "ok", ...}
```

## Subsequent Deploys

After the first setup, deploys happen automatically when you merge to `main`. You can also deploy manually:

```bash
# On the server
cd /opt/sku-ops
git pull origin main
./deploy/scripts/deploy.sh

# Or trigger from GitHub Actions (workflow_dispatch)
```

## Rollback

```bash
cd /opt/sku-ops
git log --oneline -10              # Find the commit to roll back to
git reset --hard <commit-sha>
./deploy/scripts/deploy.sh
```

---

## Managed Platform Deployment (Recommended)

For a managed hosting setup, the app runs as two separate services plus a managed database.

### Architecture

```
Frontend (static site)  →  app.yourdomain.com
Backend  (Docker)       →  api.yourdomain.com
Database (managed PG)   →  provided by platform
Redis                   →  Upstash / platform add-on (free tier works)
```

### Frontend (Static Site)

Deploy `frontend/` as a static site on Render, DigitalOcean App Platform, or similar.

- **Build command:** `npm ci && npm run build`
- **Output directory:** `dist`
- **Environment variable:** `VITE_BACKEND_URL=https://api.yourdomain.com`
- **Rewrite rule:** All routes → `index.html` (SPA fallback)

### Backend (Docker Web Service)

Deploy `backend/` using the Dockerfile. The platform must support Docker-based deploys
(needed for `tesseract-ocr` and `poppler-utils` system packages).

- **Dockerfile path:** `backend/Dockerfile`
- **Health check:** `GET /api/health`
- **Required env vars:**
  - `ENV=production`
  - `DATABASE_URL=postgresql://user:pass@host:5432/dbname`
  - `JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">`
  - `CORS_ORIGINS=https://app.yourdomain.com`
  - `FRONTEND_URL=https://app.yourdomain.com`
- **Optional env vars:** `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
  `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, `XERO_REDIRECT_URI`, `SENTRY_DSN`,
  `REDIS_URL` (required when `WORKERS > 1`; enables cross-worker event hub, sessions, and sync locks),
  `WORKERS` (default 1; set > 1 with `REDIS_URL` for multi-worker mode),
  `PG_POOL_MIN` (default 2), `PG_POOL_MAX` (default 10),
  `PG_COMMAND_TIMEOUT` (default 60s), `PG_ACQUIRE_TIMEOUT` (default 30s — pool acquire timeout, prevents unbounded hangs under load)

### Database

Use a managed Postgres instance from the same provider or Neon/Supabase Postgres.
The backend auto-creates tables on first startup.

### WebSocket Support

The backend exposes two WebSocket endpoints:

- `GET /api/ws` — realtime domain event broadcasting (inventory, withdrawals, material requests)
- `GET /api/ws/chat` — AI assistant streaming

Ensure the platform supports WebSocket connections (both Render and DO App Platform do).

**Important production constraints:**

- **Multi-worker mode:** Set `REDIS_URL` to enable `WORKERS > 1`. With Redis, the event hub uses Pub/Sub (all workers receive domain events), chat sessions are stored as Redis hashes, and the Xero sync lock is a distributed Redis key. Without Redis, the server refuses to start with `WORKERS > 1`.
- The client reconnects automatically with exponential backoff (1s–30s). Heartbeat timeout is 45s — if no ping is received within that window, the client closes and reconnects. This handles half-open connections and NAT timeouts transparently.
- If a subscriber's event queue fills (256 events, e.g. a very slow client), the server closes that connection cleanly so the client can reconnect rather than silently orphaning it.
- The BM25/embedding search index is rebuilt per-worker on startup and automatically refreshed when `inventory.updated` or `catalog.updated` events arrive via the event hub.

### Domain and HTTPS

- Buy a domain and create DNS records for `app` (frontend) and `api` (backend)
- HTTPS is managed by the platform — no Nginx/Certbot needed

### First Admin Bootstrap

Public registration is disabled in production. Create the first admin by running
the seed script against the managed database, or use the dev seed endpoint locally
before deploying.

### Launch Checklist

1. Provision managed Postgres and note the connection string
2. Provision Redis (Upstash free tier or platform add-on) and note the URL
3. Deploy backend Docker service with env vars (including `REDIS_URL`)
4. Deploy frontend static site with `VITE_BACKEND_URL`
5. Attach domain, verify HTTPS
6. Create first admin user
7. Test admin and contractor flows on desktop and iPad Safari
8. Invite real users
