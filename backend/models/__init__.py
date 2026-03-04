"""Pydantic models for the API."""
from identity.domain.user import (
    ROLES,
    User,
    UserCreate,
    UserLogin,
    UserUpdate,
)
from catalog.domain.department import Department, DepartmentCreate
from catalog.domain.vendor import Vendor, VendorCreate
from catalog.domain.product import (
    Product,
    ProductCreate,
    ProductUpdate,
    ExtractedProduct,
)
from .withdrawal import (
    MaterialWithdrawal,
    MaterialWithdrawalCreate,
    WithdrawalItem,
)
from .material_request import (
    MaterialRequest,
    MaterialRequestCreate,
    MaterialRequestProcess,
)
from inventory.domain.stock import StockTransaction, StockTransactionType
from .invoice import Invoice, InvoiceLineItem, InvoiceCreate, InvoiceUpdate, InvoiceWithDetails, InvoiceSyncXeroBulk

__all__ = [
    "ROLES",
    "User",
    "UserCreate",
    "UserLogin",
    "UserUpdate",
    "Department",
    "DepartmentCreate",
    "Vendor",
    "VendorCreate",
    "Product",
    "ProductCreate",
    "ProductUpdate",
    "ExtractedProduct",
    "MaterialWithdrawal",
    "MaterialWithdrawalCreate",
    "WithdrawalItem",
    "MaterialRequest",
    "MaterialRequestCreate",
    "MaterialRequestProcess",
    "StockTransaction",
    "StockTransactionType",
    "Invoice",
    "InvoiceLineItem",
    "InvoiceCreate",
    "InvoiceUpdate",
    "InvoiceWithDetails",
    "InvoiceSyncXeroBulk",
]
