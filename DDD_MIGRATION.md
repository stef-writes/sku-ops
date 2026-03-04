# SKU-Ops Backend — DDD Migration Plan

**Goal:** Restructure the backend into eight bounded contexts following Domain-Driven Design.
No feature changes. No regressions. No legacy stubs left behind.

---

## Guiding Principles

1. **Bounded contexts own their full vertical slice** — domain, application, infrastructure, API layers all live inside the context folder.
2. **No cross-context direct imports** — contexts communicate through shared domain value objects or explicit ports (Protocol classes).
3. **Shared kernel is minimal** — only truly cross-cutting infrastructure: DB connection, config, base exceptions.
4. **Domain models are pure Pydantic** — no HTTP or DB coupling. Already the case; keep it.
5. **Application layer orchestrates, doesn't know HTTP** — services receive plain Python types, not `Request` objects.
6. **Each phase leaves tests green** — run `pytest` after every phase before moving on.

---

## Final Directory Tree (Exact End State)

```
backend/
├── server.py                              # FastAPI bootstrap only (lifespan, middleware, router composition)
│
├── shared/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── exceptions.py                  # ← domain/exceptions.py (unchanged)
│   │   └── value_objects.py               # NEW: Money, UOM constants, SKU slug helpers
│   └── infrastructure/
│       ├── __init__.py
│       ├── config.py                      # ← config.py (unchanged)
│       ├── database.py                    # ← db.py: connection + transaction mgmt only
│       └── migrations/
│           ├── __init__.py
│           ├── runner.py                  # NEW: sequential migration runner (replaces ALTER TABLE soup)
│           ├── 001_initial_schema.sql     # All CREATE TABLE statements extracted from db.py
│           ├── 002_vendor_barcode.sql
│           ├── 003_uom_columns.sql
│           ├── 004_multi_tenant.sql
│           ├── 005_departments_org_unique.sql
│           ├── 006_invoice_line_items_cost.sql
│           ├── 007_org_settings.sql
│           ├── 008_xero_fields.sql
│           ├── 009_invoice_job_id.sql
│           └── 010_memory_artifacts.sql
│
├── identity/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── user.py                        # ← models/user.py
│   │   ├── organisation.py               # ← models/organization.py
│   │   └── org_settings.py               # ← models/org_settings.py
│   ├── application/
│   │   ├── __init__.py
│   │   └── auth_service.py               # ← auth.py (hash_password, verify_password, create_token, get_current_user, require_role)
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── user_repo.py                  # ← repositories/user_repo.py
│   │   ├── org_repo.py                   # ← repositories/organization_repo.py
│   │   └── org_settings_repo.py          # ← repositories/org_settings_repo.py
│   └── api/
│       ├── __init__.py
│       ├── auth.py                        # ← api/auth.py
│       ├── settings.py                    # ← api/settings.py
│       └── seed.py                        # ← api/seed.py
│
├── catalog/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── product.py                     # ← models/product.py (ProductCreate, ProductUpdate, Product, ExtractedProduct)
│   │   ├── vendor.py                      # ← models/vendor.py
│   │   ├── department.py                  # ← models/department.py
│   │   └── barcode.py                     # ← domain/barcode.py (validate_upc, validate_ean13, validate_barcode)
│   ├── ports/
│   │   ├── __init__.py
│   │   └── repositories.py               # ← ports/repositories.py (ProductRepository, DepartmentRepository, VendorRepository protocols)
│   ├── application/
│   │   ├── __init__.py
│   │   ├── product_lifecycle.py          # ← services/product_lifecycle.py
│   │   └── sku_service.py                # ← services/sku_service.py + services/sku_slug.py (merged)
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── product_repo.py               # ← repositories/product_repo.py
│   │   ├── vendor_repo.py                # ← repositories/vendor_repo.py
│   │   ├── department_repo.py            # ← repositories/department_repo.py
│   │   └── sku_repo.py                   # ← repositories/sku_repo.py
│   └── api/
│       ├── __init__.py
│       ├── products.py                    # ← api/products.py
│       ├── vendors.py                     # ← api/vendors.py
│       ├── departments.py                 # ← api/departments.py
│       └── sku.py                         # ← api/sku.py
│
├── inventory/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── stock.py                       # ← models/stock.py
│   ├── application/
│   │   ├── __init__.py
│   │   ├── inventory_service.py          # ← services/inventory.py
│   │   └── uom_classifier.py             # ← services/uom_classifier.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── stock_repo.py                 # ← repositories/stock_repo.py
│   └── api/
│       ├── __init__.py
│       └── stock.py                       # Stock adjustment + history endpoints (extracted from api/products.py)
│
├── operations/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── withdrawal.py                  # ← models/withdrawal.py
│   │   └── material_request.py           # ← models/material_request.py
│   ├── application/
│   │   ├── __init__.py
│   │   └── withdrawal_service.py         # ← services/withdrawal_service.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── withdrawal_repo.py            # ← repositories/withdrawal_repo.py
│   │   └── material_request_repo.py      # ← repositories/material_request_repo.py
│   └── api/
│       ├── __init__.py
│       ├── withdrawals.py                 # ← api/withdrawals.py
│       ├── material_requests.py          # ← api/material_requests.py
│       └── contractors.py                # ← api/contractors.py
│
├── purchasing/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── purchase_order.py             # NEW: PO domain model (Pydantic, extracted from api/purchase_orders.py inline schemas)
│   ├── application/
│   │   ├── __init__.py
│   │   └── purchase_order_service.py     # ← services/purchase_order_service.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── po_repo.py                    # ← repositories/po_repo.py
│   └── api/
│       ├── __init__.py
│       └── purchase_orders.py            # ← api/purchase_orders.py
│
├── finance/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── invoice.py                    # ← models/invoice.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── payment_port.py               # ← ports/payment.py (PaymentGateway protocol)
│   │   └── xero_port.py                  # ← ports/xero.py (XeroGateway protocol)
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── payment_factory.py            # ← adapters/payment_factory.py
│   │   ├── stripe_adapter.py             # ← adapters/stripe_payment.py (renamed for clarity)
│   │   ├── stub_payment.py               # ← adapters/stub_payment.py
│   │   ├── xero_adapter.py               # ← adapters/xero_adapter.py
│   │   ├── stub_xero.py                  # ← adapters/stub_xero.py
│   │   └── xero_factory.py               # ← adapters/xero_factory.py
│   ├── application/
│   │   ├── __init__.py
│   │   └── invoice_service.py            # NEW: invoice business logic extracted from api/invoices.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── invoice_repo.py               # ← repositories/invoice_repo.py
│   │   └── payment_repo.py               # ← repositories/payment_repo.py
│   └── api/
│       ├── __init__.py
│       ├── invoices.py                    # ← api/invoices.py
│       ├── financials.py                  # ← api/financials.py
│       ├── payments.py                    # ← api/payments.py
│       ├── webhooks.py                    # ← api/webhooks.py
│       └── xero_auth.py                  # ← api/xero_auth.py
│
├── documents/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── document.py                   # NEW: DocumentImportRequest domain model
│   ├── application/
│   │   ├── __init__.py
│   │   ├── ocr_service.py                # ← services/ocr_parse.py
│   │   ├── import_parser.py              # ← services/document_import.py (pure parsing logic)
│   │   ├── enrichment_service.py         # ← services/document_enrichment.py
│   │   └── import_service.py             # ← services/document_import_service.py (orchestrator)
│   └── api/
│       ├── __init__.py
│       └── documents.py                  # ← api/documents.py
│
├── assistant/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── conversation.py               # NEW: Session/thread entity (extracted from session_store.py)
│   ├── application/
│   │   ├── __init__.py
│   │   ├── llm.py                         # ← services/llm.py
│   │   ├── assistant.py                   # ← services/assistant.py
│   │   └── session_store.py              # ← services/session_store.py (stores keyed by session_id)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── agent_utils.py                # ← services/agents/agent_utils.py
│   │   ├── deps.py                        # ← services/agents/deps.py
│   │   ├── general.py                     # ← services/agents/general.py
│   │   ├── inventory.py                   # ← services/agents/inventory.py
│   │   ├── ops.py                         # ← services/agents/ops.py
│   │   ├── finance.py                     # ← services/agents/finance.py
│   │   ├── insights.py                    # ← services/agents/insights.py
│   │   ├── search.py                      # ← services/agents/search.py
│   │   ├── memory_extract.py             # ← services/agents/memory_extract.py
│   │   └── memory_store.py               # ← services/agents/memory_store.py
│   └── api/
│       ├── __init__.py
│       └── chat.py                        # ← api/chat.py
│
├── reports/
│   ├── __init__.py
│   └── api/
│       ├── __init__.py
│       ├── reports.py                     # ← api/reports.py
│       └── dashboard.py                   # ← api/dashboard.py
│
└── tests/
    ├── conftest.py
    ├── shared/
    ├── identity/
    ├── catalog/
    │   ├── test_barcode_validation.py     # ← tests/test_barcode_validation.py
    │   └── test_product_lifecycle.py      # ← tests/test_product_lifecycle.py
    ├── inventory/
    │   └── test_inventory.py              # ← tests/test_inventory.py
    ├── operations/
    │   └── test_withdrawal_service.py     # ← tests/test_withdrawal_service.py
    ├── finance/
    │   ├── test_invoice_repo.py           # ← tests/test_invoice_repo.py
    │   └── test_stripe_payments.py        # ← tests/test_stripe_payments.py
    ├── assistant/
    │   ├── test_llm_anthropic.py          # ← tests/test_llm_anthropic.py
    │   └── test_memory.py                 # ← tests/test_memory.py
    └── documents/
```

---

## Files Deleted at End of Migration

These root-level directories are fully dissolved:

| Deleted | Replaced by |
|---|---|
| `domain/` | `shared/domain/` + `catalog/domain/barcode.py` |
| `models/` | Per-context `domain/` layers |
| `ports/` | `catalog/ports/` + `finance/ports/` |
| `adapters/` | `finance/adapters/` |
| `repositories/` | Per-context `infrastructure/` layers |
| `services/` | Per-context `application/` + `assistant/agents/` |
| `api/` | Per-context `api/` layers |
| `auth.py` | `identity/application/auth_service.py` |
| `config.py` | `shared/infrastructure/config.py` |
| `db.py` | `shared/infrastructure/database.py` + `migrations/` |

---

## Migration Phases

Each phase: create new structure → move files with updated imports → update all importers → delete old files → `pytest`.

---

### Phase 0 — Prep (no moves yet)

**Goal:** Safety net before touching anything.

1. Confirm all tests pass: `pytest tests/ -q`
2. Commit current state: `git commit -am "pre-ddd snapshot"`
3. Add `conftest.py` `sys.path` awareness — tests must work from `backend/` root throughout migration.

---

### Phase 1 — Shared Kernel

**Move:**
- `config.py` → `shared/infrastructure/config.py`
- `db.py` (connection mgmt only) → `shared/infrastructure/database.py`
- `domain/exceptions.py` → `shared/domain/exceptions.py`
- Create `shared/domain/value_objects.py` with `ALLOWED_BASE_UNITS` constant (extracted from `models/product.py`)

**Migrations refactor:**
- Extract every `CREATE TABLE` block from `db.py:init_db()` into `shared/infrastructure/migrations/001_initial_schema.sql`
- Extract each `ALTER TABLE` batch into numbered SQL files (`002_vendor_barcode.sql` through `010_memory_artifacts.sql`)
- Write `shared/infrastructure/migrations/runner.py`:
  - `migrations` table tracks applied versions
  - `run_migrations(conn)` reads `*.sql` files in order, skips already-applied
  - `init_db()` becomes: connect → WAL → FK → `run_migrations()` only

**Update importers:**
- `server.py` → `from shared.infrastructure.config import ...`, `from shared.infrastructure.database import ...`, `from shared.domain.exceptions import ...`
- All files that import from root-level `config`, `db`, `domain.exceptions` — update in-place

**Delete:** `config.py`, `db.py`, `domain/` (both files)

**Test:** `pytest`

---

### Phase 2 — Identity Context

**Move:**
- `auth.py` → `identity/application/auth_service.py`
- `models/user.py` → `identity/domain/user.py`
- `models/organization.py` → `identity/domain/organisation.py`
- `models/org_settings.py` → `identity/domain/org_settings.py`
- `repositories/user_repo.py` → `identity/infrastructure/user_repo.py`
- `repositories/organization_repo.py` → `identity/infrastructure/org_repo.py`
- `repositories/org_settings_repo.py` → `identity/infrastructure/org_settings_repo.py`
- `api/auth.py` → `identity/api/auth.py`
- `api/settings.py` → `identity/api/settings.py`
- `api/seed.py` → `identity/api/seed.py`

**Update importers:** Every file importing `from auth import`, `from repositories.user_repo import`, `from models.user import`, `from models.org_settings import`.

**server.py:** Remove `from api.seed import ...`. Call `identity.api.seed` equivalents via lifespan.

**Delete:** `auth.py`, `models/user.py`, `models/organization.py`, `models/org_settings.py`, `repositories/user_repo.py`, `repositories/organization_repo.py`, `repositories/org_settings_repo.py`, `api/auth.py`, `api/settings.py`, `api/seed.py`

**Test:** `pytest`

---

### Phase 3 — Catalog Context

**Move:**
- `domain/barcode.py` → `catalog/domain/barcode.py`
- `models/product.py` → `catalog/domain/product.py`
  - Move `ALLOWED_BASE_UNITS` → import from `shared/domain/value_objects.py`
- `models/vendor.py` → `catalog/domain/vendor.py`
- `models/department.py` → `catalog/domain/department.py`
- `ports/repositories.py` (Product/Department/Vendor protocols only) → `catalog/ports/repositories.py`
- `services/product_lifecycle.py` → `catalog/application/product_lifecycle.py`
- `services/sku_service.py` + `services/sku_slug.py` → `catalog/application/sku_service.py` (merged into one file)
- `repositories/product_repo.py` → `catalog/infrastructure/product_repo.py`
- `repositories/vendor_repo.py` → `catalog/infrastructure/vendor_repo.py`
- `repositories/department_repo.py` → `catalog/infrastructure/department_repo.py`
- `repositories/sku_repo.py` → `catalog/infrastructure/sku_repo.py`
- `api/products.py` → `catalog/api/products.py`
- `api/vendors.py` → `catalog/api/vendors.py`
- `api/departments.py` → `catalog/api/departments.py`
- `api/sku.py` → `catalog/api/sku.py`

**Update importers:** All files importing from `models.product`, `models.vendor`, `models.department`, `services.product_lifecycle`, `services.sku_service`, `services.sku_slug`, `repositories.product_repo`, etc.

**Delete:** Listed source files above.

**Test:** `pytest`

---

### Phase 4 — Inventory Context

**Move:**
- `models/stock.py` → `inventory/domain/stock.py`
- `services/inventory.py` → `inventory/application/inventory_service.py`
- `services/uom_classifier.py` → `inventory/application/uom_classifier.py`
- `repositories/stock_repo.py` → `inventory/infrastructure/stock_repo.py`

**Extract:** Stock adjustment + stock history endpoints from `catalog/api/products.py` → `inventory/api/stock.py`
(Product CRUD stays in catalog; `/products/{id}/adjust`, `/products/{id}/history` move to inventory)

**Update importers:** All files importing inventory-related services and repos.

**server.py:** Include `inventory/api/stock.py` router.

**Delete:** `models/stock.py`, `services/inventory.py`, `services/uom_classifier.py`, `repositories/stock_repo.py`

**Test:** `pytest`

---

### Phase 5 — Operations Context

**Move:**
- `models/withdrawal.py` → `operations/domain/withdrawal.py`
- `models/material_request.py` → `operations/domain/material_request.py`
- `services/withdrawal_service.py` → `operations/application/withdrawal_service.py`
- `repositories/withdrawal_repo.py` → `operations/infrastructure/withdrawal_repo.py`
- `repositories/material_request_repo.py` → `operations/infrastructure/material_request_repo.py`
- `api/withdrawals.py` → `operations/api/withdrawals.py`
- `api/material_requests.py` → `operations/api/material_requests.py`
- `api/contractors.py` → `operations/api/contractors.py`

**Update importers:** Files importing from above paths.

**Delete:** Listed source files.

**Test:** `pytest`

---

### Phase 6 — Purchasing Context

**Move:**
- `services/purchase_order_service.py` → `purchasing/application/purchase_order_service.py`
- `repositories/po_repo.py` → `purchasing/infrastructure/po_repo.py`
- `api/purchase_orders.py` → `purchasing/api/purchase_orders.py`

**Extract:** Inline Pydantic schemas from `api/purchase_orders.py` → `purchasing/domain/purchase_order.py`

**Update importers:** Files importing PO service and repo.

**Delete:** Listed source files.

**Test:** `pytest`

---

### Phase 7 — Finance Context

**Move:**
- `models/invoice.py` → `finance/domain/invoice.py`
- `ports/payment.py` → `finance/ports/payment_port.py`
- `ports/xero.py` → `finance/ports/xero_port.py`
  - Update `xero_port.py`: change `from models.org_settings import` → `from identity.domain.org_settings import`
- `adapters/payment_factory.py` → `finance/adapters/payment_factory.py`
- `adapters/stripe_payment.py` → `finance/adapters/stripe_adapter.py`
- `adapters/stub_payment.py` → `finance/adapters/stub_payment.py`
- `adapters/xero_adapter.py` → `finance/adapters/xero_adapter.py`
- `adapters/stub_xero.py` → `finance/adapters/stub_xero.py`
- `adapters/xero_factory.py` → `finance/adapters/xero_factory.py`
- `repositories/invoice_repo.py` → `finance/infrastructure/invoice_repo.py`
- `repositories/payment_repo.py` → `finance/infrastructure/payment_repo.py`
- `api/invoices.py` → `finance/api/invoices.py`
- `api/financials.py` → `finance/api/financials.py`
- `api/payments.py` → `finance/api/payments.py`
- `api/webhooks.py` → `finance/api/webhooks.py`
- `api/xero_auth.py` → `finance/api/xero_auth.py`

**Extract:** Invoice business logic from `finance/api/invoices.py` → `finance/application/invoice_service.py`

**Update importers:** All `from adapters.`, `from ports.`, `from models.invoice`, `from repositories.invoice_repo`, `from repositories.payment_repo` imports.

**Delete:** Listed source files. `adapters/`, `ports/` directories fully dissolved.

**Test:** `pytest`

---

### Phase 8 — Documents Context

**Move:**
- `services/ocr_parse.py` → `documents/application/ocr_service.py`
- `services/document_import.py` → `documents/application/import_parser.py`
- `services/document_import_service.py` → `documents/application/import_service.py`
- `services/document_enrichment.py` → `documents/application/enrichment_service.py`
- `api/documents.py` → `documents/api/documents.py`

**Extract:** `DocumentImportRequest` schema → `documents/domain/document.py`

**Fix known issue:** `enrichment_service.py:84-86` — replace bare `except Exception: pass` with explicit error logging and typed exception handling.

**Update importers:** Files importing document services.

**Delete:** Listed source files.

**Test:** `pytest`

---

### Phase 9 — Assistant Context

**Move:**
- `services/llm.py` → `assistant/application/llm.py`
- `services/assistant.py` → `assistant/application/assistant.py`
- `services/session_store.py` → `assistant/application/session_store.py`
- `services/agents/agent_utils.py` → `assistant/agents/agent_utils.py`
- `services/agents/deps.py` → `assistant/agents/deps.py`
- `services/agents/general.py` → `assistant/agents/general.py`
- `services/agents/inventory.py` → `assistant/agents/inventory.py`
- `services/agents/ops.py` → `assistant/agents/ops.py`
- `services/agents/finance.py` → `assistant/agents/finance.py`
- `services/agents/insights.py` → `assistant/agents/insights.py`
- `services/agents/search.py` → `assistant/agents/search.py`
- `services/agents/memory_extract.py` → `assistant/agents/memory_extract.py`
- `services/agents/memory_store.py` → `assistant/agents/memory_store.py`
- `api/chat.py` → `assistant/api/chat.py`

**Extract:** `ChatRequest` schema from `api/schemas.py` → `assistant/api/schemas.py`

**Delete:** `services/` directory fully dissolved. `api/schemas.py` (remaining schemas go to their contexts — `DocumentImportRequest` → `documents/domain/document.py`, `CreatePaymentRequest` → `finance/api/schemas.py`, `SuggestUomRequest` → `inventory/api/schemas.py`).

**Test:** `pytest`

---

### Phase 10 — Reports Context + Final Cleanup

**Move:**
- `api/reports.py` → `reports/api/reports.py`
- `api/dashboard.py` → `reports/api/dashboard.py`
- `api/health.py` → `reports/api/health.py` (or keep at root — health has no domain)

**Reorganise tests:**
- Move each test file to match its context (see Final Directory Tree above)
- Update `conftest.py` imports

**server.py final form:**
```python
# server.py — pure bootstrap
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from shared.infrastructure.config import CORS_ORIGINS, cors_warn_in_deployed
from shared.infrastructure.database import init_db, close_db
from shared.domain.exceptions import InsufficientStockError, ResourceNotFoundError

# Context routers
from identity.api.auth import router as auth_router
from identity.api.settings import router as settings_router
from identity.api.seed import router as seed_router, seed_mock_user, seed_standard_departments
from catalog.api.products import router as products_router
from catalog.api.vendors import router as vendors_router
from catalog.api.departments import router as departments_router
from catalog.api.sku import router as sku_router
from inventory.api.stock import router as stock_router
from operations.api.withdrawals import router as withdrawals_router
from operations.api.material_requests import router as material_requests_router
from operations.api.contractors import router as contractors_router
from purchasing.api.purchase_orders import router as purchase_orders_router
from finance.api.invoices import router as invoices_router
from finance.api.financials import router as financials_router
from finance.api.payments import router as payments_router
from finance.api.webhooks import router as webhooks_router
from finance.api.xero_auth import router as xero_auth_router
from documents.api.documents import router as documents_router
from assistant.api.chat import router as chat_router
from reports.api.reports import router as reports_router
from reports.api.dashboard import router as dashboard_router
from reports.api.health import router as health_router
```

**Delete:** `api/` directory fully dissolved.

**Verify nothing remains in old locations:**
```bash
find backend/ -maxdepth 1 -name "*.py" | grep -vE "(server|conftest)\.py"
# → only server.py should remain at root
ls backend/
# → server.py, shared/, identity/, catalog/, inventory/, operations/,
#    purchasing/, finance/, documents/, assistant/, reports/, tests/, data/, scripts/
```

**Test:** `pytest` — full suite must pass.

---

### Phase 11 — Import Validation

Run import checks to confirm no cross-context coupling:

```bash
# No context should import from another context's infrastructure layer
grep -r "from catalog.infrastructure" assistant/ operations/ finance/ reports/
grep -r "from finance.infrastructure" catalog/ assistant/ inventory/
# → should return empty
```

**Acceptable cross-context imports:**
- Any context → `shared.domain.*`, `shared.infrastructure.*`
- `assistant.agents.*` → any context's `application.*` (agents query data from all domains — this is acceptable via explicit service interfaces, not repos)
- `documents.application.*` → `catalog.application.*` (enrichment resolves departments/vendors)
- `finance.ports.xero_port` → `identity.domain.org_settings` (OrgSettings is a value object here)

---

## Tech Debt Eliminated

| Debt | Resolution |
|---|---|
| `db.py` inline ALTER TABLE soup | Versioned SQL migration files + runner |
| `domain/` ghost folder | Dissolved; logic moved to owning contexts |
| `services/` junk drawer | Dissolved; each service in its context |
| `api/schemas.py` global blob | Schemas co-located with their context |
| `services/sku_slug.py` orphan | Merged into `catalog/application/sku_service.py` |
| `adapters/` disconnected from `ports/` | Both co-located in `finance/` |
| `ports/repositories.py` global | Split per context into `catalog/ports/` |
| Silent exception swallowing in enrichment | Fixed in Phase 8 |
| Tests flat in `tests/` | Reorganised by bounded context |

---

## Execution Order Summary

```
Phase 0  Prep + baseline test run
Phase 1  Shared kernel (config, db, exceptions, migrations)
Phase 2  Identity (auth, users, orgs, settings)
Phase 3  Catalog (products, vendors, departments, SKU, barcode)
Phase 4  Inventory (stock, UOM)
Phase 5  Operations (withdrawals, material requests, contractors)
Phase 6  Purchasing (purchase orders)
Phase 7  Finance (invoices, payments, Xero adapters)
Phase 8  Documents (OCR, import, enrichment)
Phase 9  Assistant (LLM, agents, chat)
Phase 10 Reports + final cleanup
Phase 11 Import validation
```

Every phase is independently committable. The app runs correctly after each one.
