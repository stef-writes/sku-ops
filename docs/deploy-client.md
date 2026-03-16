# Deploy for a New Client

Per-client deployment on Railway + Vercel + Supabase.

For the full deployment guide and architecture diagram, see [DEPLOY.md](../DEPLOY.md).

## Prerequisites

- A Supabase project (one per client)
- Railway connected to the GitHub repo
- Vercel connected to the GitHub repo
- Env var templates: `deploy/railway-env.example`, `deploy/vercel-env.example`

## 1. Set up Supabase

1. Create a new Supabase project at [supabase.com](https://supabase.com)
2. Collect from **Settings > API**:
   - Project URL (`https://xxxx.supabase.co`)
   - Anon key (`eyJ...`)
   - JWT Secret (under "JWT Settings")
3. Collect from **Settings > Database**:
   - Direct connection string (port **5432**, NOT 6543)

## 2. Deploy the backend (Railway)

1. Copy `deploy/railway-env.example` into Railway dashboard > Settings > Variables
2. Fill in all `REQUIRED` values:
   - `ENV=production`
   - `DATABASE_URL` — Supabase direct connection string
   - `JWT_SECRET` — Supabase JWT secret (must match exactly)
   - `CORS_ORIGINS` — Vercel production domain(s)
3. Add a Railway Redis service and set `REDIS_URL` if using `WORKERS > 1`
4. Set `FRONTEND_URL` to the Vercel domain (needed for Xero OAuth redirects)
5. Deploy and check logs for:
   ```
   INFO  Application ready — env=production, auth_provider=supabase, ...
   ```

Schema is bootstrapped automatically on first startup.

## 3. Deploy the frontend (Vercel)

1. Copy `deploy/vercel-env.example` into Vercel dashboard > Project Settings > Environment Variables
2. Fill in:
   - `VITE_BACKEND_URL` — Railway deployment URL (no trailing slash)
   - `VITE_SUPABASE_URL` — Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` — Supabase anon key
3. Trigger a redeploy (VITE_* vars are baked at build time)
4. Note all stable Vercel domains and add them to Railway's `CORS_ORIGINS`

## 4. Create the admin user in Supabase

Sign up the admin via the Supabase dashboard (Authentication > Users), then set their role
in the Supabase SQL Editor:

```sql
UPDATE auth.users
SET raw_app_meta_data = jsonb_set(
  COALESCE(raw_app_meta_data, '{}'::jsonb),
  '{role}', '"admin"'
)
WHERE email = 'admin@clientname.com';
```

Get the Supabase user UUID:

```sql
SELECT id FROM auth.users WHERE email = 'admin@clientname.com';
```

## 5. Create the local profile row

The backend `users` table holds enriched profile data (company, phone, billing entity).
Create a row so `/api/auth/me` returns full data:

```bash
DATABASE_URL=<production-connection-string> \
./bin/dev create-admin \
  --id <supabase-user-uuid> \
  --email admin@clientname.com \
  --name "Client Admin" \
  --org-id default
```

## 6. Rename the default org (optional)

The schema seeds a `"default"` org on first startup. Rename it to the client:

```sql
UPDATE organizations SET name = 'ClientName', slug = 'clientname' WHERE id = 'default';
```

## 7. Verify

```bash
./bin/dev verify --url https://your-railway-app.up.railway.app
```

Check that:
- `/api/health` returns 200 with `env=production`
- `/api/ready` returns 200 with all checks passing
- Login via Supabase SDK works in the browser
- `/api/auth/me` returns the enriched profile
- No CORS errors in browser console
- WebSocket connects (check Network tab for `/api/ws`)

## Quick Checklist

- [ ] Supabase project created
- [ ] Railway env vars set (see `deploy/railway-env.example`)
- [ ] Vercel env vars set (see `deploy/vercel-env.example`)
- [ ] All Vercel domains added to Railway `CORS_ORIGINS`
- [ ] Admin user created in Supabase Auth
- [ ] `app_metadata.role` set to `"admin"` in Supabase SQL Editor
- [ ] Local profile row created via `create-admin`
- [ ] `./bin/dev verify --url <railway-url>` passes
- [ ] Login works in browser
- [ ] `/api/auth/me` returns full profile
