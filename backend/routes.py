"""Route aggregation — collects all context routers into a single api_router."""

from fastapi import APIRouter

from assistant.api.chat import router as chat_router
from assistant.api.monitoring import router as monitoring_router
from assistant.api.ws_chat import router as ws_chat_router
from catalog.api.departments import router as departments_router
from catalog.api.products import router as products_router
from catalog.api.sku import router as sku_router
from catalog.api.vendors import router as vendors_router
from documents.api.documents import router as documents_router
from finance.api.credit_notes import router as credit_notes_router
from finance.api.financials import router as financials_router
from finance.api.fiscal_periods import router as fiscal_periods_router
from finance.api.invoices import router as invoices_router
from finance.api.payments import router as payments_router
from finance.api.xero_auth import router as xero_auth_router
from finance.api.xero_health import router as xero_health_router
from identity.api.addresses import router as addresses_router
from identity.api.audit import router as audit_router
from identity.api.auth import router as auth_router
from identity.api.billing_entities import router as billing_entities_router
from identity.api.settings import router as settings_router
from inventory.api.cycle_counts import router as cycle_counts_router
from inventory.api.stock import router as stock_router
from jobs.api.jobs import router as jobs_router
from operations.api.contractors import router as contractors_router
from operations.api.material_requests import router as material_requests_router
from operations.api.returns import router as returns_router
from operations.api.withdrawals import router as withdrawals_router
from purchasing.api.purchase_orders import router as purchase_orders_router
from reports.api.dashboard import router as dashboard_router
from reports.api.reports import router as reports_router
from shared.api.health import router as health_router
from shared.api.websocket import router as ws_router
from shared.infrastructure.config import is_development, is_test

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(health_router)
api_router.include_router(sku_router)
api_router.include_router(chat_router)
api_router.include_router(monitoring_router)
api_router.include_router(contractors_router)
api_router.include_router(departments_router)
api_router.include_router(vendors_router)
api_router.include_router(products_router)
api_router.include_router(stock_router)
api_router.include_router(cycle_counts_router)
api_router.include_router(withdrawals_router)
api_router.include_router(material_requests_router)
api_router.include_router(purchase_orders_router)
api_router.include_router(financials_router)
api_router.include_router(invoices_router)
api_router.include_router(returns_router)
api_router.include_router(credit_notes_router)
api_router.include_router(payments_router)
api_router.include_router(fiscal_periods_router)
api_router.include_router(reports_router)
api_router.include_router(dashboard_router)
api_router.include_router(documents_router)
api_router.include_router(addresses_router)
api_router.include_router(billing_entities_router)
api_router.include_router(jobs_router)
if is_development or is_test:
    try:
        from devtools.api.seed import router as seed_router

        api_router.include_router(seed_router)
    except ImportError:
        pass
api_router.include_router(settings_router)
api_router.include_router(xero_auth_router)
api_router.include_router(xero_health_router)
api_router.include_router(ws_router)
api_router.include_router(ws_chat_router)


@api_router.get("/")
async def root():
    return {"message": "Supply Yard API - Material Management System"}
