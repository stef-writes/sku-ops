# SKU Central - Hardware Store Management System PRD

## Original Problem Statement
Build a complete hardware storefront, POS, inventory management system multi-page app for inventory, vendor, and POS. It needs its own SKU system, departments, and alignment with stores like Home Depot, Lowes, etc.

## User Choices
- JWT-based custom auth (email/password)
- Stripe integration (MOCKED for now)
- Standard hardware departments + custom departments
- Sales/inventory reports
- Receipt upload with OCR using Gemini 3 Flash

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI
- **Backend**: FastAPI + MongoDB
- **Auth**: JWT-based authentication
- **AI**: Gemini 3 Flash for receipt OCR

## User Personas
1. **Store Owner/Admin**: Full access to all features, reports, and settings
2. **Store Manager**: Access to POS, inventory, vendors, and reports
3. **Employee/Cashier**: Access to POS and limited inventory viewing

## Core Requirements (Static)
- [x] User authentication (register/login)
- [x] Dashboard with sales overview and alerts
- [x] POS system with cart and checkout
- [x] Inventory management with SKU generation
- [x] Vendor management
- [x] Department management
- [x] Receipt OCR import (Gemini 3 Flash)
- [x] Sales and inventory reports

## SKU System
Format: `DEPT-XXXXX` (e.g., LUM-00001, PLU-00002)
- LUM: Lumber
- PLU: Plumbing
- ELE: Electrical
- PNT: Paint
- TOL: Tools
- HDW: Hardware
- GDN: Garden
- APP: Appliances

## What's Been Implemented (Feb 23, 2026)
1. **Authentication**: JWT-based login/register with role support
2. **Dashboard**: Real-time stats, recent sales, low stock alerts
3. **POS**: Product search, cart management, checkout with cash/card
4. **Inventory**: Full CRUD, SKU auto-generation, department filtering
5. **Vendors**: Full CRUD with contact info
6. **Departments**: 8 pre-seeded + custom department creation
7. **Receipt Import**: Upload receipt → AI extraction → SKU conversion
8. **Reports**: Sales analytics with charts, inventory reports

## Prioritized Backlog

### P0 (Critical) - DONE
- [x] Core POS functionality
- [x] Inventory CRUD with SKUs
- [x] Basic authentication

### P1 (Important) - DONE
- [x] Receipt OCR import
- [x] Sales reports
- [x] Low stock alerts

### P2 (Nice to Have)
- [ ] Barcode scanning integration
- [ ] Purchase order management
- [ ] Multi-store support
- [ ] Employee shift management
- [ ] Print receipts/invoices

## Next Tasks
1. Add actual Stripe payment processing
2. Implement barcode scanner support
3. Add purchase order creation for vendors
4. Multi-location/store support
5. Export reports to PDF/Excel
