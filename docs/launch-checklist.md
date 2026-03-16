# Launch Checklist

Production readiness checklist for sku-ops. Work through each section before going live.

---

## Infrastructure

- [ ] Provision managed Postgres (Supabase, Neon, or DO managed DB) and note the direct connection string (port 5432, not pooler)
- [ ] Provision Redis (Upstash free tier or platform add-on) and note the URL
- [ ] Set `REDIS_URL` and `WORKERS=2` (or more) in production environment
- [ ] Verify multi-worker startup succeeds with Redis (`docker compose up` logs show "Redis connected" and "multi-worker mode is safe")
- [ ] Configure automated Postgres backups (daily, 7-day retention) — see `deploy/scripts/backup-postgres.sh`
- [ ] Set up Sentry project and configure `SENTRY_DSN`
- [ ] Set `METRICS_TOKEN` and configure Prometheus scraping or platform metrics dashboard
- [ ] Configure uptime monitoring on `/api/health` and `/api/ready` (UptimeRobot, Better Stack, or similar)
- [ ] Point DNS A records for frontend and API subdomains
- [ ] Provision TLS certificates (auto via Certbot on VPS, or platform-managed)

## Security

- [ ] Generate production `JWT_SECRET`: `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set `CORS_ORIGINS` to exact production domain(s) — no wildcards
- [ ] Verify security headers with [securityheaders.com](https://securityheaders.com): `X-Frame-Options`, `CSP`, `HSTS`, `X-Content-Type-Options`
- [ ] Confirm nginx rate limiting is active (60 req/min API, 10 req/min auth, 20 req/min chat)
- [ ] Audit git history for committed secrets: `git log --all -p -- '*.env' '*.pem' '*.key'`
- [ ] Verify `ALLOW_RESET=false` in production (`config.py` enforces this automatically for production)
- [ ] Verify demo seed endpoints are disabled in production
- [ ] Ensure `.env` files are in `.gitignore` and `.dockerignore`

## Data Integrity

- [ ] Run full seed and verify all CRUD workflows end-to-end:
  - [ ] Create product, set stock levels, verify inventory counts
  - [ ] Create withdrawal (POS), verify stock decremented
  - [ ] Create invoice from withdrawal, transition draft -> approved -> paid
  - [ ] Create and apply credit note
  - [ ] Xero sync: invoice syncs, reconciliation matches, COGS journal posts
- [ ] Test Xero OAuth flow end-to-end with real credentials (connect, sync, disconnect)
- [ ] Verify WebSocket events propagate to all connected clients (open 2+ browser tabs, create withdrawal, both should update)
- [ ] Test contractor flow: login -> search products -> add to cart -> submit material request -> staff processes -> verify withdrawal created
- [ ] Test admin flow: POS terminal -> scan/search items -> process withdrawal -> generate invoice -> record payment
- [ ] Verify document import: upload receipt PDF -> AI parses line items -> creates purchase order

## CI/CD

- [ ] Verify `ci.yml` passes on both `dev` and `main` branches (backend lint + format + test, frontend lint + format + build + test, Docker build)
- [ ] Verify `bump.yml` creates version tags and GitHub releases on merge to `main`
- [ ] Verify `deploy.yml` SSH deploy completes successfully on merge to `main`
- [ ] Create GitHub environment `production` with required reviewers
- [ ] Add branch protection rules for `main`: require PR, require status checks (Backend, Frontend, Docker build), require up-to-date
- [ ] Add branch protection rules for `dev`: require PR, require status checks (Backend, Frontend)
- [ ] Run `cz bump --dry-run` to verify commitizen config produces correct version tags
- [ ] Verify `CHANGELOG.md` gets populated on first real bump
- [ ] Install pre-commit hooks locally: `uv run --directory backend pre-commit install --install-hooks && uv run --directory backend pre-commit install --hook-type commit-msg`

## Testing

- [ ] All backend tests pass: `cd backend && uv run pytest -v` (currently 421+ tests)
- [ ] All frontend tests pass: `cd frontend && npm test -- --run`
- [ ] Ruff lint clean: `cd backend && uv run ruff check .`
- [ ] Ruff format clean: `cd backend && uv run ruff format --check .`
- [ ] ESLint clean: `cd frontend && npx eslint src/`
- [ ] Prettier clean: `cd frontend && npx prettier --check src/`
- [ ] Architecture tests pass (DDD boundary enforcement): `cd backend && uv run pytest tests/test_architecture.py -v`
- [ ] WebSocket edge case tests pass (fan-out, filtering, rapid reconnect)
- [ ] Integration workflow tests pass (authenticated CRUD flows)

## Observability

- [ ] Verify JSON structured logging in production: deploy with `LOG_LEVEL=INFO`, check logs contain `request_id`, `user_id`, `org_id` fields
- [ ] Confirm `X-Request-ID` response header is present on all API responses
- [ ] Trigger a test error in Sentry and verify it arrives with `org_id` and `request_id` tags
- [ ] Set up log aggregation (journald on VPS, or ship to Datadog/Loki/CloudWatch)
- [ ] Verify Prometheus metrics at `/metrics` (requires `METRICS_TOKEN` auth): `http_requests_total`, `http_request_duration_seconds`

## Post-Launch (Not Blockers)

- [ ] Add database migration tooling (alembic or custom) before the first schema change with live data
- [ ] Expand frontend test coverage (currently 3 test files — add tests for critical pages and hooks)
- [ ] Add load testing with k6 or locust (target: 50 concurrent users, measure p95 latency)
- [ ] Add E2E browser tests (Playwright) for contractor and admin critical flows
- [ ] Set up a staging environment for pre-production validation
- [ ] Add Redis health check to `/api/ready` endpoint
- [ ] Configure alerting rules (error rate spikes, p95 latency > 2s, health check failures)
