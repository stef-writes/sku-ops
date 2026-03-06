"""Document domain models for receipt/invoice parsing and archival."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import AuditedEntity


class DocumentLineItem(BaseModel):
    """Line item from a parsed document — local to the documents context."""
    name: str
    original_sku: str | None = None
    quantity: float = 1
    ordered_qty: float | None = None
    delivered_qty: float | None = None
    price: float = 0.0
    cost: float | None = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    suggested_department: str | None = None
    product_id: str | None = None
    selected: bool = True
    ai_parsed: bool = False


class DocumentImportRequest(BaseModel):
    """Request to import a parsed document into a purchase order."""
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: str | None = None
    products: list[DocumentLineItem]


class DocumentType(str, Enum):
    RECEIPT = "receipt"
    INVOICE = "invoice"
    PACKING_SLIP = "packing_slip"
    OTHER = "other"


class DocumentStatus(str, Enum):
    PARSED = "parsed"
    IMPORTED = "imported"
    REJECTED = "rejected"


class Document(AuditedEntity):
    """Persisted record of an uploaded and parsed document."""
    filename: str
    document_type: str = DocumentType.OTHER
    vendor_name: str | None = None
    file_hash: str = ""
    file_size: int = 0
    mime_type: str = ""
    parsed_data: str | None = None
    po_id: str | None = None
    status: str = DocumentStatus.PARSED
    uploaded_by_id: str
