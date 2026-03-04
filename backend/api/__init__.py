"""
API package - aggregates all routers for the main app.
"""
from fastapi import APIRouter

from identity.api.auth import router as auth_router
from assistant.api.chat import router as chat_router
from reports.api.health import router as health_router
from operations.api.contractors import router as contractors_router
from reports.api.dashboard import router as dashboard_router
from catalog.api.departments import router as departments_router
from documents.api.documents import router as documents_router
from finance.api.financials import router as financials_router
from finance.api.invoices import router as invoices_router
from finance.api.payments import router as payments_router
from catalog.api.products import router as products_router
from reports.api.reports import router as reports_router
from catalog.api.sku import router as sku_router
from catalog.api.vendors import router as vendors_router
from finance.api.webhooks import router as webhooks_router
from operations.api.withdrawals import router as withdrawals_router
from operations.api.material_requests import router as material_requests_router
from purchasing.api.purchase_orders import router as purchase_orders_router
from identity.api.seed import router as seed_router
from identity.api.settings import router as settings_router
from finance.api.xero_auth import router as xero_auth_router
from assistant.api.monitoring import router as monitoring_router

api_router = APIRouter(prefix="/api")

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(sku_router)
api_router.include_router(chat_router)
api_router.include_router(monitoring_router)
api_router.include_router(contractors_router)
api_router.include_router(departments_router)
api_router.include_router(vendors_router)
api_router.include_router(products_router)
api_router.include_router(withdrawals_router)
api_router.include_router(material_requests_router)
api_router.include_router(purchase_orders_router)
api_router.include_router(financials_router)
api_router.include_router(invoices_router)
api_router.include_router(reports_router)
api_router.include_router(dashboard_router)
api_router.include_router(documents_router)
api_router.include_router(payments_router)
api_router.include_router(webhooks_router)
api_router.include_router(seed_router)
api_router.include_router(settings_router)
api_router.include_router(xero_auth_router)


@api_router.get("/")
async def root():
    return {"message": "Supply Yard API - Material Management System"}
