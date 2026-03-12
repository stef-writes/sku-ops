"""Purchase order domain models.

PurchaseOrder and PurchaseOrderItem are the canonical entities.
POItemCreate is the typed DTO for incoming line items (from document parse or API).
Status enums and transition rules live here — no free-form strings.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel

from shared.kernel.constants import DEFAULT_ORG_ID
from shared.kernel.entity import AuditedEntity, Entity

# ── Status enums ───────────────────────────────────────────────────────────────


class POStatus(StrEnum):
    ORDERED = "ordered"
    PARTIAL = "partial"
    RECEIVED = "received"


class POItemStatus(StrEnum):
    ORDERED = "ordered"
    PENDING = "pending"  # delivery arrived at dock, not yet received into inventory
    ARRIVED = "arrived"  # received into inventory


# ── Entities ───────────────────────────────────────────────────────────────────


class PurchaseOrder(AuditedEntity):
    vendor_id: str
    vendor_name: str = ""
    document_date: str | None = None
    total: float | None = None
    status: POStatus = POStatus.ORDERED
    notes: str | None = None
    created_by_id: str = ""
    created_by_name: str = ""
    received_at: str | None = None
    received_by_id: str | None = None
    received_by_name: str | None = None
    organization_id: str = DEFAULT_ORG_ID

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
    original_sku: str | None = None
    ordered_qty: float = 1
    delivered_qty: float = 0
    unit_price: float = 0.0
    cost: float = 0.0
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    suggested_department: str = "HDW"
    status: POItemStatus = POItemStatus.ORDERED
    product_id: str | None = None
    organization_id: str = DEFAULT_ORG_ID

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


class CreatePORequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: str | None = None
    document_date: str | None = None
    total: float | None = None
    products: list[POItemCreate]


class ReceiveItemUpdate(BaseModel):
    id: str
    delivered_qty: float | None = None
    product_id: str | None = None
    name: str | None = None
    cost: float | None = None
    unit_price: float | None = None
    suggested_department: str | None = None
    base_unit: str | None = None
    sell_uom: str | None = None
    pack_qty: int | None = None
    barcode: str | None = None


class ReceiveItemsRequest(BaseModel):
    items: list[ReceiveItemUpdate]


class MarkDeliveryRequest(BaseModel):
    item_ids: list[str]
