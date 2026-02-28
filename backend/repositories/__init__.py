"""Repository layer for SQLite data access."""
from .user_repo import user_repo
from .department_repo import department_repo
from .vendor_repo import vendor_repo
from .product_repo import product_repo
from .withdrawal_repo import withdrawal_repo
from .payment_repo import payment_repo
from .sku_repo import sku_repo
from .stock_repo import stock_repo

__all__ = [
    "user_repo",
    "department_repo",
    "vendor_repo",
    "product_repo",
    "withdrawal_repo",
    "payment_repo",
    "sku_repo",
    "stock_repo",
]
