"""
API package - aggregates all routers for the main app.
"""
from fastapi import APIRouter

from .auth import router as auth_router
from .chat import router as chat_router
from .health import router as health_router
from .contractors import router as contractors_router
from .dashboard import router as dashboard_router
from .departments import router as departments_router
from .documents import router as documents_router
from .financials import router as financials_router
from .invoices import router as invoices_router
from .payments import router as payments_router
from .products import router as products_router
from .reports import router as reports_router
from .sku import router as sku_router
from .vendors import router as vendors_router
from .webhooks import router as webhooks_router
from .withdrawals import router as withdrawals_router
from .material_requests import router as material_requests_router
from .purchase_orders import router as purchase_orders_router
from .seed import router as seed_router
from .settings import router as settings_router
from .xero_auth import router as xero_auth_router

api_router = APIRouter(prefix="/api")

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(sku_router)
api_router.include_router(chat_router)
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
