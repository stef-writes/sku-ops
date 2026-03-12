# Deployment Playbook

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Vercel     │     │   Railway    │     │   Supabase   │
│  (Frontend)  │────▶│  (Backend)   │────▶│  (Postgres)  │
│  React SPA   │     │  FastAPI     │     │  Port 5432   │
└──────────────┘     └──────────────┘     └──────────────┘
  Deploys from:        Deploys from:        Managed DB
  main branch          main branch
  Root dir: frontend/  Dockerfile: backend/
```

- **Frontend** (Vercel) — static React SPA, talks directly to backend via `VITE_BACKEND_URL`
- **Backend** (Railway) — FastAPI in Docker, connects to Supabase Postgres via `DATABASE_URL`
- **Database** (Supabase) — Postgres 16. Use the **direct** connection (port 5432), NOT the pooler (port 6543). asyncpg uses prepared statements which are incompatible with pgbouncer.

There is also a **self-hosted** path via `docker-compose.yml` (Postgres + Redis + backend + nginx + certbot) — this is an alternative to the Vercel/Railway/Supabase stack for VPS deployments.

---

## Environments

| Environment | `ENV` value | Where | Purpose |
|---|---|---|---|
| **Local dev** | `development` | Your machine | SQLite, no secrets needed, demo seed auto-loads |
| **Staging** | `staging` | Railway + Vercel + Supabase | Real Postgres, demo auth enabled |
| **Production** | `production` | Same stack, strict config | No demo auth, no reset endpoints, Supabase Auth required |

### Staging vs Production differences

| Behavior | `staging` | `production` |
|---|---|---|
| JWT_SECRET | Must be set, not default | Must be set, not default |
| CORS_ORIGINS | Must be set, not `*` | Must be set, not `*` |
| `ALLOW_PUBLIC_AUTH` | Can be `true` (local login/register) | Should be removed (Supabase Auth only) |
| `ALLOW_RESET` | Can be `true` (seed endpoint) | Should be removed |
| Demo user seed | Only if `DEMO_USER_EMAIL` set | Never — even if vars are set |

### Promoting staging → production

1. Set `ENV=production` on Railway
2. Remove `ALLOW_PUBLIC_AUTH` and `ALLOW_RESET`
3. Set `JWT_SECRET` to your Supabase project's JWT secret (Dashboard > Settings > API)
4. Set `app_metadata.role` on all Supabase users (see "Adding users" below)
5. Update `CORS_ORIGINS` to production domain(s)

---

## Branching Strategy

**Single-branch workflow:** `main` is the deploy branch for both Vercel and Railway.

- All work goes through PRs into `main`
- Vercel auto-deploys preview URLs for PRs, production on merge to `main`
- Railway auto-deploys on push to `main`

The `dev` branch exists but is currently unused (identical to `main`). If you want staging/prod split later, use `dev` → Railway staging, `main` → Railway production.

---

## Vercel (Frontend)

**Project:** `frontend`
**Root config:** `vercel.json` (repo root — controls monorepo build)
**Framework:** Vite

### How the build works

Vercel uses the root `vercel.json`:
```json
{
  "buildCommand": "cd frontend && npm ci && npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "echo skip",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

The SPA rewrite ensures React Router works on hard refresh. No API proxy needed — the frontend talks directly to Railway via `VITE_BACKEND_URL`.

### Environment variables (Vercel dashboard)

| Variable | Value | Notes |
|---|---|---|
| `VITE_BACKEND_URL` | `https://your-app.up.railway.app` | No trailing slash. All API calls go here. |
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` | Supabase Dashboard > Settings > API |
| `VITE_SUPABASE_ANON_KEY` | `eyJ...` | Supabase Dashboard > Settings > API |

These are **build-time** variables (baked into JS). Changing them requires a redeploy.

### Production domains

Stable domains (must be in Railway's `CORS_ORIGINS`):
- `frontend-five-ecru-30.vercel.app` (custom alias)
- `frontend-stefanos-projects-915294ee.vercel.app` (project domain)
- `frontend-git-main-stefanos-projects-915294ee.vercel.app` (branch domain)

Preview deployments get unique URLs — these are NOT in CORS_ORIGINS by default.

---

## Railway (Backend)

**Config:** `railway.toml` (repo root)
**Dockerfile:** `backend/Dockerfile`
**Health check:** `GET /api/health`

### Environment variables

**Required (app won't start without these):**

| Variable | Value | Notes |
|---|---|---|
| `ENV` | `staging` or `production` | Controls strictness |
| `DATABASE_URL` | `postgresql://...@host:5432/db` | Port 5432 (direct), NOT 6543 (pooler) |
| `JWT_SECRET` | Supabase JWT secret or random hex | Must match what signs tokens |
| `CORS_ORIGINS` | Comma-separated Vercel URLs | Must include all stable frontend domains |

**Optional:**

| Variable | Value | Notes |
|---|---|---|
| `ALLOW_PUBLIC_AUTH` | `true` | Enables `/api/auth/login` and `/api/auth/register` |
| `ALLOW_RESET` | `true` | Enables `/api/reset` seed endpoint |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Enables AI assistant |
| `REDIS_URL` | `redis://...` | Required if `WORKERS > 1` |
| `WORKERS` | `1` | Uvicorn worker count |
| `SENTRY_DSN` | `https://...@sentry.io/...` | Error tracking |
| `FRONTEND_URL` | `https://your-app.vercel.app` | For OAuth callback redirects |

### Updating env vars

```bash
railway variables --set "CORS_ORIGINS=https://domain1.com,https://domain2.com"
```
Railway auto-redeploys on variable change.

### Manual redeploy

```bash
railway up        # Deploy from local code
# or just push to main — Railway auto-deploys
```

---

## Docker Compose (Self-Hosted Alternative)

For VPS deployments without Vercel/Railway/Supabase.

```bash
# Dev (local)
docker compose up          # Uses docker-compose.override.yml automatically
                           # Exposes Postgres:5433, backend:8000
                           # Skips nginx/certbot

# Production (VPS)
cp .env.production.example .env    # Fill in secrets
docker compose -f docker-compose.yml up -d    # Ignores override, runs full stack
```

---

## Database

### Local dev
SQLite at `backend/data/sku_ops.db` — auto-created, auto-migrated, auto-seeded.

### Staging/Production
Supabase Postgres 16. Migrations run automatically on startup.

### SQL compatibility rules

The codebase supports both SQLite and Postgres:
- All queries use `?` placeholders — auto-converted to `$N` for Postgres
- `ROUND(SUM(...))` **must** use `CAST(... AS NUMERIC)` — Postgres rejects `round(real, integer)`
- SQLite-specific functions (`julianday`, `datetime`) **must** use helpers from `shared/infrastructure/db/sql_compat.py`
- `INSERT OR IGNORE` is auto-converted to `INSERT ... ON CONFLICT DO NOTHING`

### Connection rules
- Port **5432** (direct), NOT 6543 (Supabase pgbouncer)
- Backend raises RuntimeError on startup if port 6543 detected in deployed environments

---

## CI/CD Pipeline

**GitHub Actions:** `.github/workflows/ci.yml`

| Job | What it does |
|---|---|
| `backend` | Lint (ruff) + format check + tests against **SQLite** |
| `backend-postgres` | Same tests against **Postgres 16** (catches SQL dialect bugs) |
| `frontend` | Lint (eslint) + format (prettier) + build + tests (vitest) |
| `docker` | Builds the backend Docker image (build smoke test) |

Runs on push to `main`/`dev` and on PRs targeting those branches.

---

## Initial Setup (First Deploy)

### 1. Supabase — collect credentials

From **Supabase Dashboard > Settings > API**:
- Project URL (`https://xxxx.supabase.co`)
- Anon key (`eyJ...`)
- JWT Secret (under "JWT Settings" — **not** the anon key)

### 2. Railway — set env vars

Set all required variables (see table above). Deploy and check logs for:
```
INFO  Application ready — env=staging, db=postgres, ...
```

### 3. Vercel — set build-time env vars

Set `VITE_BACKEND_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Trigger redeploy.

### 4. Provision admin user

If using Supabase Auth:
1. Create user in Supabase Dashboard > Authentication > Users
2. Run `create_admin.py` with their UUID
3. Set `app_metadata.role` in Supabase SQL Editor:
```sql
UPDATE auth.users
SET raw_app_meta_data = jsonb_set(
  COALESCE(raw_app_meta_data, '{}'::jsonb),
  '{role}', '"admin"'
)
WHERE email = 'you@example.com';
```

If using local auth (`ALLOW_PUBLIC_AUTH=true`):
- Hit `/api/reset` to seed demo data, or register via `/api/auth/register`

### 5. Smoke test

```bash
curl https://<railway-domain>/api/health   # → {"status":"ok",...}
curl https://<railway-domain>/api/ready    # → {"status":"ok","checks":{...}}
```

Open the Vercel URL, log in, check browser console for CORS errors.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| WebSocket 403 | `CORS_ORIGINS` missing frontend domain | Add Vercel URL to Railway `CORS_ORIGINS` |
| Every API request 401 | JWT_SECRET mismatch, or `app_metadata.role` not set | Check JWT_SECRET matches token signer |
| `round(real, integer)` error | Missing `CAST(... AS NUMERIC)` in SQL | Wrap: `ROUND(CAST(expr AS NUMERIC), 2)` |
| `julianday` does not exist | SQLite function in Postgres query | Use `sql_compat.days_overdue_expr()` |
| Frontend blank / can't reach backend | `VITE_BACKEND_URL` wrong or missing | Set in Vercel env vars, redeploy |
| DB connection fails | Using port 6543 (pgbouncer) | Switch to port 5432 (direct) |
| Backend crashes on startup | Missing required env var | Read the RuntimeError message |

### Useful commands

```bash
# Check Railway env vars
railway variables --json | python3 -c "import sys,json; [print(f'{k}={v}') for k,v in sorted(json.load(sys.stdin).items())]"

# Check Railway logs
railway logs

# Verify backend health
curl https://<railway-domain>/api/ready

# Trigger Railway redeploy
railway up
```
