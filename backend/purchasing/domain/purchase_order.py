"""Purchase order domain models.

PurchaseOrder and PurchaseOrderItem are the canonical entities.
POItemCreate is the typed DTO for incoming line items (from document parse or API).
Status enums and transition rules live here — no free-form strings.
"""
from enum import Enum
from typing import ClassVar, List, Optional

from pydantic import BaseModel

from kernel.entity import AuditedEntity, Entity


# ── Status enums ───────────────────────────────────────────────────────────────

class POStatus(str, Enum):
    ORDERED = "ordered"
    PARTIAL = "partial"
    RECEIVED = "received"


class POItemStatus(str, Enum):
    ORDERED = "ordered"
    PENDING = "pending"    # delivery arrived at dock, not yet received into inventory
    ARRIVED = "arrived"    # received into inventory


# ── Entities ───────────────────────────────────────────────────────────────────

class PurchaseOrder(AuditedEntity):
    vendor_id: str
    vendor_name: str = ""
    document_date: Optional[str] = None
    total: Optional[float] = None
    status: POStatus = POStatus.ORDERED
    notes: Optional[str] = None
    created_by_id: str = ""
    created_by_name: str = ""
    received_at: Optional[str] = None
    received_by_id: Optional[str] = None
    received_by_name: Optional[str] = None
    organization_id: str = "default"

    ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "ordered": {"partial", "received"},
        "partial": {"received"},
        "received": set(),
    }

    def can_transition_to(self, target: str) -> bool:
        return target in self.ALLOWED_TRANSITIONS.get(self.status.value, set())


class PurchaseOrderItem(Entity):
    po_id: str
    name: str
    original_sku: Optional[str] = None
    ordered_qty: float = 1
    delivered_qty: float = 0
    unit_price: float = 0.0
    cost: float = 0.0
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    suggested_department: str = "HDW"
    status: POItemStatus = POItemStatus.ORDERED
    product_id: Optional[str] = None
    organization_id: str = "default"

    ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "ordered": {"pending"},
        "pending": {"arrived"},
        "arrived": set(),
    }

    def can_transition_to(self, target: str) -> bool:
        return target in self.ALLOWED_TRANSITIONS.get(self.status.value, set())


# ── Request DTOs ───────────────────────────────────────────────────────────────

class POItemCreate(BaseModel):
    """Typed input for a single PO line item (from document parse or manual entry)."""
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


class CreatePORequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: Optional[str] = None
    document_date: Optional[str] = None
    total: Optional[float] = None
    products: List[POItemCreate]


class ReceiveItemUpdate(BaseModel):
    id: str
    delivered_qty: Optional[float] = None


class ReceiveItemsRequest(BaseModel):
    items: List[ReceiveItemUpdate]


class MarkDeliveryRequest(BaseModel):
    item_ids: List[str]
