"""Repository layer for SQLite data access."""
from identity.infrastructure.user_repo import user_repo
from identity.infrastructure.org_repo import organization_repo
from .department_repo import department_repo
from .vendor_repo import vendor_repo
from .product_repo import product_repo
from .withdrawal_repo import withdrawal_repo
from .material_request_repo import material_request_repo
from .payment_repo import payment_repo
from .sku_repo import sku_repo
from .stock_repo import stock_repo
from .invoice_repo import invoice_repo

__all__ = [
    "user_repo",
    "organization_repo",
    "department_repo",
    "vendor_repo",
    "product_repo",
    "withdrawal_repo",
    "material_request_repo",
    "payment_repo",
    "sku_repo",
    "stock_repo",
    "invoice_repo",
]
