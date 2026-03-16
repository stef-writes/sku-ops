# Deployment Playbook

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Vercel     │     │   Railway    │     │   Supabase   │
│  (Frontend)  │────▶│  (Backend)   │────▶│  (Auth + DB) │
│  React SPA   │     │  FastAPI     │     │  Postgres 16 │
└──────────────┘     └──────────────┘     └──────────────┘
  Deploys from:        Deploys from:        Managed
  main branch          main branch
  Root dir: /          Dockerfile: backend/
```

- **Frontend** (Vercel) — static React SPA, talks directly to backend via `VITE_BACKEND_URL`
- **Backend** (Railway) — FastAPI in Docker, connects to Supabase Postgres via `DATABASE_URL`
- **Auth** (Supabase) — issues JWTs. Backend validates them using Supabase's `JWT_SECRET`.
- **Database** (Supabase Postgres) — port **5432 (direct)**, NOT 6543 (pooler). asyncpg uses prepared statements which are incompatible with pgbouncer.

There is also a **self-hosted** path via `docker-compose.yml` (Postgres + Redis + backend + nginx + certbot). See `docs/deployment.md` for VPS instructions.

---

## Environments

| Environment | `ENV` value | Where | Purpose |
|---|---|---|---|
| Local dev | `development` | Your machine | Postgres via docker-compose.dev.yml, permissive defaults |
| Test | `test` | CI / local pytest | Test Postgres DB, conftest sets this |
| Production | `production` | Railway + Vercel + Supabase | Strict config, Supabase Auth required |

There is no staging environment. `config.py` accepts exactly three values: `development`, `test`, `production`.

### Production guards (hard startup errors, not warnings)

| Guard | What happens |
|---|---|
| `JWT_SECRET` missing or dev default | `RuntimeError` — app refuses to start |
| `CORS_ORIGINS` is `*` or empty | `RuntimeError` — app refuses to start |
| `ALLOW_RESET=true` | `RuntimeError` — seed/reset endpoint would be exposed |
| `ALLOW_PUBLIC_AUTH=true` | `RuntimeError` — local login/register would be exposed |
| `DATABASE_URL` not PostgreSQL | `RuntimeError` |

---

## New Client Deployment (Step by Step)

### 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. From **Settings > API**, collect:
   - **Project URL** — `https://xxxx.supabase.co`
   - **Anon key** — `eyJ...` (public, safe for frontend)
   - **JWT Secret** — under "JWT Settings" (this is NOT the anon key)
3. From **Settings > Database**, collect:
   - **Connection string** — use the **Direct** connection (port 5432), NOT the pooler (port 6543)
   - Format: `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres`

### 2. Deploy backend on Railway

1. Connect your GitHub repo to Railway
2. Railway uses `railway.toml` at the repo root:
   ```toml
   [build]
   builder = "DOCKERFILE"
   dockerfilePath = "backend/Dockerfile"
   buildContextPath = "."

   [deploy]
   healthcheckPath = "/api/health"
   healthcheckTimeout = 30
   restartPolicyType = "ON_FAILURE"
   restartPolicyMaxRetries = 3
   ```
3. Set environment variables in Railway dashboard (see `deploy/railway-env.example` for the full list):

   **Required — app won't start without these:**

   | Variable | Value | Notes |
   |---|---|---|
   | `ENV` | `production` | |
   | `DATABASE_URL` | `postgresql://...` | Supabase direct connection, port 5432 |
   | `JWT_SECRET` | Supabase JWT secret | Dashboard > Settings > API > JWT Secret |
   | `CORS_ORIGINS` | `https://your-app.vercel.app` | Comma-separated. Include all Vercel domains. |

   **Recommended:**

   | Variable | Value | Notes |
   |---|---|---|
   | `REDIS_URL` | `redis://...` | Add a Railway Redis service. Required if `WORKERS > 1`. |
   | `FRONTEND_URL` | `https://your-app.vercel.app` | Required for Xero OAuth redirects |
   | `SENTRY_DSN` | `https://...@sentry.io/...` | Error tracking |
   | `WORKERS` | `1` | Increase with Redis. Railway auto-sets `PORT`. |

   **Optional:**

   | Variable | Value | Notes |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | `sk-ant-...` | Enables AI assistant |
   | `OPENROUTER_API_KEY` | `sk-or-...` | Alternative AI provider |
   | `OPENAI_API_KEY` | `sk-...` | Product search embeddings |
   | `CORS_ORIGIN_REGEX` | `https://frontend-.*\.vercel\.app` | Allow Vercel preview deploys |
   | `XERO_CLIENT_ID` | | Xero integration |
   | `XERO_CLIENT_SECRET` | | Xero integration |
   | `XERO_REDIRECT_URI` | `https://your-railway.app/api/xero/callback` | Xero integration |
   | `PG_POOL_MAX` | `10` | Tune: `floor(max_pg_connections / WORKERS)` |
   | `LOG_LEVEL` | `INFO` | |

4. Deploy. Check Railway logs for:
   ```
   INFO  Application ready — env=production, auth_provider=supabase, db=..., ...
   ```

### 3. Deploy frontend on Vercel

1. Import the repo on Vercel. The root `vercel.json` handles the monorepo build:
   ```json
   {
     "buildCommand": "cd frontend && npm ci && npm run build",
     "outputDirectory": "frontend/dist",
     "installCommand": "echo skip"
   }
   ```
2. Set environment variables in Vercel dashboard > Settings > Environment Variables:

   | Variable | Value | Notes |
   |---|---|---|
   | `VITE_BACKEND_URL` | `https://your-app.up.railway.app` | No trailing slash. All API calls go here. |
   | `VITE_SUPABASE_URL` | `https://xxxx.supabase.co` | From Supabase Dashboard > Settings > API |
   | `VITE_SUPABASE_ANON_KEY` | `eyJ...` | From Supabase Dashboard > Settings > API |

   These are **build-time** variables (baked into JS). Changing them requires a redeploy.

3. After first deploy, note all stable Vercel domains and add them to Railway's `CORS_ORIGINS`:
   - The custom alias domain
   - The project domain (`frontend-xxx.vercel.app`)
   - The branch domain (`frontend-git-main-xxx.vercel.app`)

### 4. Create the organization

The schema creates a `"default"` org on first startup. Rename it for the client:

```sql
UPDATE organizations SET name = 'ClientName', slug = 'clientname' WHERE id = 'default';
```

For additional tenants, insert a new row:

```sql
INSERT INTO organizations (id, name, slug, created_at) VALUES ('client2', 'Client Two', 'client2', NOW());
```

### 5. Create the admin user

1. Create the user in **Supabase Dashboard > Authentication > Users** (email + password)
2. Set the admin role **and** `organization_id` in **Supabase SQL Editor**:
   ```sql
   UPDATE auth.users
   SET raw_app_meta_data = jsonb_set(
     jsonb_set(
       COALESCE(raw_app_meta_data, '{}'::jsonb),
       '{role}', '"admin"'
     ),
     '{organization_id}', '"default"'
   )
   WHERE email = 'admin@clientname.com';
   ```
   **The `organization_id` claim is required.** Without it, the backend rejects every request with 401 in production. The value must match an `organizations.id` row in the database.

3. Get the Supabase user UUID:
   ```sql
   SELECT id FROM auth.users WHERE email = 'admin@clientname.com';
   ```
4. Create the local profile row so `/api/auth/me` returns enriched data (company, phone, billing_entity):
   ```bash
   DATABASE_URL=<production-db-url> \
   ./bin/dev create-admin \
     --id <supabase-user-uuid> \
     --email admin@clientname.com \
     --name "Client Admin" \
     --org-id default
   ```

### 6. Verify

```bash
./bin/dev verify --url https://your-railway-app.up.railway.app
```

Check that:
- `/api/health` returns 200 with `env=production`
- `/api/ready` returns 200 with all checks passing
- Login via Supabase SDK works in the browser
- `/api/auth/me` returns the enriched profile
- No CORS errors in the browser console
- WebSocket connects (check Network tab for `/api/ws`)

---

## Auth Model — Users, Contractors, Organizations

### Concepts

| Concept | What it is |
|---|---|
| **Organization** | The tenancy boundary. Every row in every business table has an `organization_id`. Each client gets one org. |
| **User** | A row in the `users` table. Has a `role` (`admin` or `contractor`), scoped to one `organization_id`. |
| **Admin** | `role = 'admin'`. Full access: inventory, purchasing, invoicing, reports, settings, AI assistant. |
| **Contractor** | `role = 'contractor'`. Limited access: can view products (no cost), create material requests, view their own withdrawals. Contractors have `company`, `billing_entity`, and `billing_entity_id` fields. |

Admins and contractors live in the **same `users` table** — `role` is the discriminator. There is no separate `contractors` table. The `contractor_service.py` module queries `users WHERE role = 'contractor'` and exposes CRUD via `/api/contractors`.

### How auth works

```
Frontend                  Supabase Auth              Backend
───────                   ────────────               ───────
signInWithPassword() ───▶ Validates credentials
                    ◀──── Returns JWT (access_token)

GET /api/products    ────────────────────────────▶  auth_deps.py:
  Authorization: Bearer <jwt>                         jwt.decode(token, JWT_SECRET)
                                                      auth_provider.py:
                                                        resolve_claims(payload)
                                                        → ResolvedClaims(user_id, email, role, organization_id)

                                                      CurrentUser built from claims
                                                      org_id_var.set(org_id)  ← ambient context for all repos
```

**Production (Supabase):** JWT issued by Supabase. Backend validates with Supabase's `JWT_SECRET`. Role comes from `app_metadata.role`, org from `app_metadata.organization_id`.

**Dev/test (bridge):** Backend issues its own JWT via `POST /api/auth/login`. Role and org_id are top-level claims.

### Supabase JWT claims setup

For every user in Supabase, you must set `role` and `organization_id` in `raw_app_meta_data`:

```sql
-- Admin user
UPDATE auth.users
SET raw_app_meta_data = jsonb_set(
  jsonb_set(
    COALESCE(raw_app_meta_data, '{}'::jsonb),
    '{role}', '"admin"'
  ),
  '{organization_id}', '"default"'
)
WHERE email = 'admin@clientname.com';

-- Contractor user  
UPDATE auth.users
SET raw_app_meta_data = jsonb_set(
  jsonb_set(
    COALESCE(raw_app_meta_data, '{}'::jsonb),
    '{role}', '"contractor"'
  ),
  '{organization_id}', '"default"'
)
WHERE email = 'contractor@clientname.com';
```

These values end up in the JWT as `app_metadata.role` and `app_metadata.organization_id`. The backend reads them via `auth_provider.py`.

### Adding a contractor (production workflow)

1. Admin creates the contractor via the UI or `POST /api/contractors` (which inserts into `users` with `role='contractor'`)
2. If the contractor needs to **log in themselves**, also create them in **Supabase Auth** (same email/password), then run the SQL above to set their role and org
3. If the contractor is passive (admin processes withdrawals on their behalf), skip Supabase — they only need a `users` row

### Multi-tenant isolation

- Every query in every repo calls `get_org_id()` which reads from the `org_id_var` contextvar (set from the JWT during auth)
- Every write passes `organization_id` to the insert
- Cross-org data access is impossible at the SQL level — repos always filter by `organization_id`
- In production, tokens without `organization_id` are rejected with 401 at the transport layer

### Adding a new client (new org)

1. Insert an organization row (see step 4 above)
2. Create admin user in Supabase + local profile (see step 5 above)
3. Set `organization_id` in their Supabase `app_metadata` to match the new org ID
4. All their data will be isolated to that org

---

## CI/CD Pipeline

**GitHub Actions:** `.github/workflows/ci.yml`

| Job | What it does |
|---|---|
| `backend` | Lint (ruff) + format check + pytest against Postgres 16 |
| `frontend` | Lint (eslint) + format (prettier) + build + vitest |
| `docker` | Builds the backend Docker image (smoke test) |

Runs on push to `main`/`dev` and on PRs targeting those branches.

**Auto-deploy:** Railway auto-deploys on push to `main`. Vercel auto-deploys on push to `main` (with preview deploys for PRs).

---

## WebSocket Support

Two WebSocket endpoints, both authenticated via JWT query param:

| Endpoint | Purpose |
|---|---|
| `GET /api/ws?token=...` | Realtime domain event broadcasting |
| `GET /api/ws/chat?token=...` | AI assistant streaming |

**Production constraints:**
- `REDIS_URL` required if `WORKERS > 1` (event hub uses Redis Pub/Sub)
- Client reconnects automatically with exponential backoff (1–30s)
- Heartbeat timeout: 45s (domain events), 35s (chat)

---

## Updating Environment Variables

**Railway:**
```bash
railway variables --set "CORS_ORIGINS=https://domain1.com,https://domain2.com"
```
Railway auto-redeploys on variable change.

**Vercel:**
Change in dashboard, then trigger a redeploy (VITE_* vars are baked at build time).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every API request → 401 | JWT_SECRET mismatch | Railway `JWT_SECRET` must be the Supabase JWT secret |
| 401 "missing organization_id claim" | `organization_id` not in Supabase `app_metadata` | Run the SQL to set `organization_id` in `raw_app_meta_data` |
| Login works but `/me` returns 401 | `app_metadata.role` not set | Run the SQL to set role in Supabase |
| WebSocket 403 or CORS error | `CORS_ORIGINS` missing frontend domain | Add all Vercel domains to Railway `CORS_ORIGINS` |
| Frontend blank / can't reach backend | `VITE_BACKEND_URL` wrong or missing | Set in Vercel env vars, redeploy |
| DB connection fails | Using port 6543 (pgbouncer) | Switch to port 5432 (direct) in `DATABASE_URL` |
| Backend crash on startup | Missing required env var | Read the `RuntimeError` message in Railway logs |
| Auth doesn't work at all | `@supabase/supabase-js` not installed | Run `npm install @supabase/supabase-js` in frontend/ |
| Preview deploys get CORS errors | Preview URL not in `CORS_ORIGINS` | Set `CORS_ORIGIN_REGEX` to match Vercel preview URLs |
| Xero OAuth redirect fails | `FRONTEND_URL` not set | Set to your Vercel production URL on Railway |

### Useful Commands

```bash
# Pre-deploy verification (local)
./bin/dev verify --skip-build

# Pre-deploy verification (against live server)
./bin/dev verify --url https://your-app.up.railway.app

# Check Railway logs
railway logs

# Check Railway env vars
railway variables

# Manual Railway redeploy
railway up
```

---

## Env Var Reference Files

| File | Purpose |
|---|---|
| `deploy/railway-env.example` | All Railway env vars with descriptions |
| `deploy/vercel-env.example` | All Vercel (VITE_*) env vars |
| `.env.production.example` | Docker Compose / VPS deployments |
| `backend/.env.example` | Local native development |
