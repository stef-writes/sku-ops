# SKU-Ops

Material management for supply yards — contractors, warehouses, and inventory.

## Quick Start

```bash
npm install                           # root monorepo deps (concurrently)
cd backend && uv sync --dev && cd ..  # Python deps via uv
cd frontend && npm install && cd ..   # frontend deps
cp backend/.env.example backend/.env  # edit with your keys
npm run dev                           # starts backend + frontend
```

- **Backend:** http://localhost:8000
- **Frontend:** http://localhost:3000

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@demo.local | demo123 |
| Contractor | contractor@demo.local | demo123 |

Demo users are auto-created in development. Seed full demo data with:

```bash
curl -X POST http://localhost:8000/api/seed/seed-full \
  -H "Authorization: Bearer <token>"
```

See [docs/MULTI_TENANT_DEMO_SCRIPT.md](docs/MULTI_TENANT_DEMO_SCRIPT.md) for a full walkthrough.

## Features

- **Contractors:** Request materials (search, barcode, cart) -> staff processes at pickup
- **Admin / Warehouse:** Material Terminal (POS), Pending Requests, Inventory, Financials, Invoices
- **Document Import:** AI-powered receipt/invoice parsing (Claude) with OCR fallback
- **Purchase Orders:** Review -> receive -> stock update workflow
- **AI Assistant:** Multi-agent chat with streaming via WebSocket (inventory, finance, operations)
- **Dashboard:** Revenue, margins, low stock, department P&L, daily charts (with time filters)
- **Reports:** P&L, inventory valuation, operations metrics, trend analysis
- **Invoicing:** Unpaid -> Invoiced -> Paid flows; Xero sync
- **Real-time:** WebSocket event broadcasting — UI updates automatically when data changes
- **Multi-tenant:** Org-scoped data isolation

## Tech Stack

- **Backend:** Python 3.13, FastAPI, uv (package manager), SQLite (dev) / PostgreSQL (prod)
- **Frontend:** React 18, Vite, Tailwind CSS, Radix UI, TanStack Query, ECharts
- **AI:** Anthropic Claude (documents, UOM, assistant), OpenAI (embeddings), OpenRouter (agent gateway)
- **Quality:** Ruff (Python lint + format), ESLint 9 + Prettier (frontend), CI on every push
- **Deploy:** Docker, Nginx, docker-compose, GitHub Actions CI/CD

## Dev Commands

All commands run from the project root:

```bash
npm run dev              # start backend + frontend (concurrently)
./bin/dev test [args]    # run pytest
./bin/dev lint           # lint backend (ruff)
./bin/dev fmt            # format backend (ruff)
./bin/dev lint:fe        # lint frontend (ESLint)
./bin/dev fmt:fe         # format frontend (Prettier)
./bin/dev commit         # commitizen conventional commit
./bin/dev server         # start backend only
./bin/dev ui             # start frontend only
./bin/dev container      # start devcontainer
```

## Environment

Configuration is environment-aware (`ENV=development|staging|production|test`). See `backend/.env.example` for all available settings.

| | Development | Staging | Production |
|---|---|---|---|
| JWT_SECRET | default | required | required |
| CORS | permissive (*) | required | required |
| Demo seed | auto | opt-in | disabled |
| Database | SQLite file | Postgres | Postgres |

## Architecture

```
backend/
├── api/              # Top-level router aggregation
├── identity/         # Auth, users, organizations
├── catalog/          # Products, departments, vendors, SKUs
├── inventory/        # Stock transactions, cycle counts, UOM
├── documents/        # Document parsing (OCR, AI), import logic
├── purchasing/       # Purchase orders, receiving
├── operations/       # Withdrawals, material requests, returns
├── finance/          # Invoicing, Xero integration, ledger
├── assistant/        # AI chat agents, LLM infrastructure
├── reports/          # Dashboard analytics, P&L, trends
├── jobs/             # Job definitions
├── shared/           # Config, DB, logging, metrics, middleware, WebSocket
├── devtools/         # Seed data, evals, dev-only endpoints
└── kernel/           # Shared types, errors

frontend/
├── src/
│   ├── components/   # UI components (shadcn/ui, charts, reports)
│   ├── pages/        # Route pages (finance, inventory, operations)
│   ├── hooks/        # Data hooks, useRealtimeSync, useChatSocket
│   ├── context/      # AuthContext
│   └── lib/          # API client, query client, constants
```

Each backend context owns its domain, infrastructure, and API layers. Cross-context access goes through application-layer facades, never direct infrastructure imports.

## Real-time Architecture

```
Backend domain event -> event_hub.emit() -> asyncio queues -> WebSocket /api/ws
                                                           -> WebSocket /api/ws/chat (AI streaming)

Frontend: useRealtimeSync() -> invalidates TanStack Query cache -> UI re-renders
          useChatSocket()   -> streams AI responses (delta, tool_start, done)
```

Events are org-scoped and role-filtered. Contractors only receive events relevant to their role.

## Docker

```bash
cp .env.production.example .env   # set JWT_SECRET, CORS_ORIGINS, etc.
docker compose up -d
```

The backend runs behind Nginx with the frontend served as static files from `frontend/dist`.

See [DEPLOYMENT.md](DEPLOYMENT.md) for full VPS and managed-platform deployment guides.
