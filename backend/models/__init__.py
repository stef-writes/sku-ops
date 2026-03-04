"""Pydantic models for the API."""
from identity.domain.user import (
    ROLES,
    User,
    UserCreate,
    UserLogin,
    UserUpdate,
)
from .department import Department, DepartmentCreate
from .vendor import Vendor, VendorCreate
from .product import (
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
from .stock import StockTransaction, StockTransactionType
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
