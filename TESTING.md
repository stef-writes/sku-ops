# Testing

## Prerequisites

- **Python:** 3.13+ (managed via `.python-version`)
- **uv:** 0.6+ ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Node.js:** 20+ with npm
- **Docker:** (optional, for production verification and e2e)

## Install everything

```bash
# Python tooling (backend deps + pytest + ruff + commitizen)
uv sync

# Frontend deps
npm install --prefix frontend

# Playwright (optional, for e2e tests)
cd e2e && npm install && npx playwright install --with-deps chromium && cd ..
```

`uv sync` at the workspace root installs `sku-ops-backend` as an editable workspace member plus all dev dependencies (pytest, ruff, commitizen, rich). A single `uv.lock` at the workspace root governs all Python dependencies.

## Running tests

### All tests (backend + frontend)

```bash
./bin/dev test
```

### Backend only

```bash
./bin/dev test:be                                  # all backend tests
./bin/dev test:be backend/tests/unit/              # unit tests only
./bin/dev test:be backend/tests/integration/       # integration tests only
./bin/dev test:be backend/tests/api/               # API tests only
./bin/dev test:be -k test_smoke                    # single test by name
./bin/dev test:be --tb=short -v                    # verbose with short tracebacks
```

### Frontend only

```bash
./bin/dev test:fe              # single run (vitest run)
npm run test --prefix frontend # watch mode (vitest)
```

### End-to-end (Playwright)

```bash
./bin/dev test:e2e
```

Playwright will start the backend dev server automatically if not already running.

## How imports resolve

Backend test files import production code with bare module names:

```python
from catalog.application.product_lifecycle import create_product
from shared.infrastructure.database import get_connection
from shared.kernel.types import CurrentUser
```

This works because `pythonpath = ["backend"]` in the root `pyproject.toml` pytest config adds `backend/` to `sys.path`. Combined with `--import-mode=importlib`, all backend modules resolve without `sys.path` hacks.

## Shared db fixture

A single `db` fixture lives in `backend/tests/conftest.py` and is available to all backend tests via pytest's conftest hierarchy:

```python
@pytest_asyncio.fixture
async def db():
    """Initialize in-memory SQLite, seed minimal data, teardown."""
    ...
```

It initializes an in-memory SQLite database, seeds a department (`dept-1`), an admin user (`user-1`), and a contractor user (`contractor-1`), then tears down on completion.

The `_db` fixture is an alias for `db` (many test files reference this name).

**To extend the fixture:** edit `backend/tests/conftest.py`. All backend tests inherit from it. Do not create duplicate `db` fixtures in sub-conftest files.

## Test structure

Each deployable owns its tests. E2e tests live at the workspace root.

```
backend/tests/                         # backend tests
├── conftest.py                        # env vars + shared db fixture
├── helpers/                           # shared test utilities
│   ├── auth.py                        # JWT token/header factories
│   ├── factories.py                   # domain object factories
│   └── xero.py                        # Xero mock helpers
├── unit/                              # pure logic, no DB
│   ├── test_architecture.py           # DDD boundary validation (AST-based)
│   ├── test_barcode_validation.py
│   └── ...
├── integration/                       # DB + application logic
│   ├── test_cycle_count.py
│   ├── test_product_lifecycle.py
│   └── ...
└── api/                               # HTTP tests via TestClient
    ├── conftest.py                    # client + auth_headers fixtures
    ├── test_smoke.py
    └── ...

frontend/src/                          # frontend co-located unit tests
├── hooks/__tests__/useBarcodeScanner.test.js
├── hooks/__tests__/useProductMatch.test.js
├── lib/__tests__/api-client.test.js
└── test/setup.js

e2e/                                   # cross-stack e2e (Playwright)
├── playwright.config.ts
├── package.json
└── specs/
    └── health.spec.ts
```

## Adding a new test

### Backend unit test

Create `backend/tests/unit/test_<name>.py`. Import domain/kernel code directly. No `db` fixture needed.

### Backend integration test

Create `backend/tests/integration/test_<name>.py`. Use the `db` or `_db` fixture for database access. Import application and infrastructure modules.

### Backend API test

Create `backend/tests/api/test_<name>.py`. Use the `client`, `db`, and `auth_headers` fixtures. Test through HTTP.

### Frontend unit test

Co-locate with the source file: create `frontend/src/<module>/__tests__/<name>.test.js`. Uses Vitest + jsdom + `@testing-library/react`. The `@` alias resolves to `frontend/src/`. Frontend unit tests stay inside `frontend/` because they depend on `node_modules` resolution and relative imports to source files.

### E2e test

Create `e2e/specs/<name>.spec.ts`. Uses Playwright. Server starts automatically.

## Seeds and evals

```bash
./bin/dev seed               # seed realistic demo data
./bin/dev eval --suite all   # run all LLM evals
./bin/dev eval --suite routing --model anthropic/claude-haiku-4-5
```

Seeds and evals live in `devtools/` at the workspace root. They import backend production code via `PYTHONPATH=backend:.` (set by `bin/dev`).

## Linting

```bash
./bin/dev lint     # ruff check all Python (backend + tests + devtools)
./bin/dev fmt      # ruff format all Python
./bin/dev lint:fe  # ESLint frontend
./bin/dev fmt:fe   # Prettier frontend
```

Ruff config lives in the root `pyproject.toml`. Per-file-ignores are scoped to `backend/tests/**`, `devtools/**`, and specific backend paths.

## Docker

The Docker image contains only production code and dependencies:

```bash
docker build -f backend/Dockerfile .   # build context is workspace root
```

- `uv sync --frozen --no-dev --no-editable` in the Dockerfile installs only `[project.dependencies]`.
- Devtools live at workspace root, structurally outside the `COPY backend/ .` layer.
- `backend/tests/` is excluded via `.dockerignore`.
