# Deployment Guide

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
3. CI runs automatically (lint, test, build, Docker)
4. Merge to `dev` after review
5. When `dev` is stable, open a PR from `dev` → `main`
6. Merging to `main` triggers auto-deploy to production

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
./scripts/deploy.sh
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
0 3 * * * /opt/sku-ops/scripts/backup-postgres.sh >> /var/log/sku-ops-backup.log 2>&1
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
./scripts/deploy.sh

# Or trigger from GitHub Actions (workflow_dispatch)
```

## Rollback

```bash
cd /opt/sku-ops
git log --oneline -10              # Find the commit to roll back to
git reset --hard <commit-sha>
./scripts/deploy.sh
```
