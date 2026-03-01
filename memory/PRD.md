# Supply Yard - Hardware Material Management System PRD

## Original Problem Statement
Build a complete hardware storefront, POS, and inventory management system with multi-tenancy support. The system needs its own SKU system, departments, and alignment with stores like Home Depot, Lowes, etc. Key use case: contractors withdraw materials and can either pay immediately (Stripe) or charge to their account for later invoicing.

## User Choices & Requirements
- JWT-based custom auth (email/password)
- Multi-tenancy with 3 roles: Admin, Warehouse Manager, Contractor
- Stripe integration for "Pay Now" option at POS
- "Charge to Account" option for later invoicing via Xero
- Standard hardware departments + custom departments
- Sales/inventory reports
- Receipt upload with OCR using Gemini 3 Flash
- Future: Xero integration, ServiceM8 job sync

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI
- **Backend**: FastAPI + SQLite (aiosqlite)
- **Auth**: JWT-based authentication with RBAC
- **AI**: Gemini 3 Flash for receipt OCR
- **Payments**: Stripe via emergentintegrations library

## User Personas
1. **Admin**: Full access - user management, financial dashboard, invoice exports
2. **Warehouse Manager**: POS, inventory, vendors, receipt imports
3. **Contractor**: Withdraw materials, view own history, pay or charge to account

## Core Requirements (Static)
- [x] User authentication (register/login)
- [x] Multi-tenancy with role-based access control
- [x] Dashboard with sales overview and alerts
- [x] POS (Material Withdrawal Terminal)
- [x] Inventory management with SKU generation
- [x] Vendor management
- [x] Department management
- [x] Receipt OCR import (Gemini 3 Flash)
- [x] Sales and inventory reports
- [x] Stripe "Pay Now" at POS
- [x] "Charge to Account" for later invoicing

## SKU System
Format: `DEPT-SLUG-NNNNNN` (e.g., LUM-PIPE-000001, PLU-FITT-000002)
- DEPT: Department code (3 letters, uppercase)
- SLUG: Alphanumeric derived from product name (max 6 chars), or "ITM" if empty
- NNNNNN: Zero-padded 6-digit counter per department
- Standard department codes: LUM (Lumber), PLU (Plumbing), ELE (Electrical), PNT (Paint), TOL (Tools), HDW (Hardware), GDN (Garden), APP (Appliances)

## What's Been Implemented

### Feb 24, 2026 - Stripe Payment Integration
- **Pay Now** option at POS using Stripe checkout
- Payment endpoints: `/api/payments/create-checkout`, `/api/payments/status/{session_id}`
- Stripe webhook handler at `/api/webhook/stripe`
- `payment_transactions` collection for tracking payments
- Frontend payment polling after Stripe redirect
- Both "Pay Now" and "Charge to Account" flows tested and working

### Feb 23, 2026 - Multi-Tenancy & Core System
1. **Authentication**: JWT-based login/register with 3 roles
2. **Multi-Tenancy**: Admin, Warehouse Manager, Contractor roles with RBAC
3. **Dashboard**: Role-specific stats and recent activity
4. **POS**: Material Withdrawal Terminal with contractor selection
5. **Inventory**: Full CRUD, SKU auto-generation, department filtering
6. **Vendors**: Full CRUD with PDF receipt import
7. **Departments**: 8 pre-seeded + custom department creation
8. **Receipt Import**: Upload PDF → Gemini AI extraction → SKU conversion
9. **Reports**: Sales analytics, inventory reports
10. **Financials**: Admin dashboard for paid/unpaid tracking, CSV export
11. **Contractor Management**: Admin can create/edit/deactivate contractors

## Prioritized Backlog

### P0 (Critical) - DONE
- [x] Core POS functionality
- [x] Inventory CRUD with SKUs
- [x] Basic authentication
- [x] Multi-tenancy with RBAC
- [x] Stripe "Pay Now" option

### P1 (Important)
- [ ] Xero integration for draft invoices
- [x] Receipt OCR import
- [x] Sales reports
- [x] Low stock alerts

### P2 (Nice to Have)
- [ ] ServiceM8 job sync (replace free-text Job ID with dropdown)
- [ ] Barcode scanning integration
- [ ] Purchase order management
- [ ] Print receipts/invoices

## Next Tasks
1. **Xero Integration** (P1): Generate draft invoices from unpaid "Charge to Account" transactions
2. **ServiceM8 Integration** (P2): Sync job IDs for contractor dropdown selection
3. ~~Refactor server.py into modular APIRouters~~ (partial: models, auth, db, services extracted)

## Recent Changes (Feb 26, 2026)

### Stock Ledger & Atomic Inventory
- **Stock ledger**: Every quantity change now creates an immutable `StockTransaction` record (product_id, quantity_delta, type, reference_id, user, timestamp)
- **Atomic withdrawals**: POS withdrawals use `findOneAndUpdate` with `quantity >= requested` guard; insufficient stock rolls back and returns 400
- **New API**: `GET /api/products/{product_id}/stock-history` — audit trail for any product
- **Import flows**: Receipt and vendor PDF imports now record IMPORT transactions in the ledger

### Backend Modularization
- `backend/db.py` — SQLite connection (aiosqlite), table creation, migrations on startup
- `backend/auth.py` — JWT helpers, `get_current_user`, `require_role`
- `backend/models/` — Pydantic models (user, department, vendor, product, withdrawal, stock)
- `backend/services/inventory.py` — `process_withdrawal_stock_changes`, `process_import_stock_changes`, `get_stock_history`
- SQLite indexes on products (department, sku UNIQUE, vendor), withdrawals, stock_transactions

## Test Credentials
- Admin: `admin@test.com` / `password123`
- Contractor: `contractor@test.com` / `password123`

## Database (SQLite)
- Single file: `data/sku_ops.db` (default, configurable via `DATABASE_URL`)
- Tables: users, departments, vendors, products, withdrawals, payment_transactions, sku_counters, stock_transactions
- No external DB process required

## Key API Endpoints
- Auth: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- Products: `/api/products` (GET, POST), `/api/products/{id}` (GET, PUT, DELETE)
- Vendors: `/api/vendors`
- Document Import: `/api/documents/parse`, `/api/documents/import`
- Withdrawals: `/api/withdrawals`, `/api/withdrawals/for-contractor`
- Payments: `/api/payments/create-checkout`, `/api/payments/status/{session_id}`
- Financials: `/api/financials/summary`, `/api/financials/export`
- Reports: `/api/reports/sales`, `/api/reports/inventory`
