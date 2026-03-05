"""Document domain models for receipt/invoice parsing and archival."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import AuditedEntity


class DocumentLineItem(BaseModel):
    """Line item from a parsed document — local to the documents context."""
    name: str
    original_sku: Optional[str] = None
    quantity: float = 1
    ordered_qty: Optional[float] = None
    delivered_qty: Optional[float] = None
    price: float = 0.0
    cost: Optional[float] = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    suggested_department: Optional[str] = None
    product_id: Optional[str] = None
    selected: bool = True
    ai_parsed: bool = False


class DocumentImportRequest(BaseModel):
    """Request to import a parsed document into a purchase order."""
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: Optional[str] = None
    products: List[DocumentLineItem]


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
    vendor_name: Optional[str] = None
    file_hash: str = ""
    file_size: int = 0
    mime_type: str = ""
    parsed_data: Optional[str] = None
    po_id: Optional[str] = None
    status: str = DocumentStatus.PARSED
    uploaded_by_id: str
