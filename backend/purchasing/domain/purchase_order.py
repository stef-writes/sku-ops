"""Purchase order domain models.

PurchaseOrder and PurchaseOrderItem are the canonical entities.
POItemCreate is the typed DTO for incoming line items (from document parse or API).
Status enums and transition rules live here — no free-form strings.
"""

from dataclasses import dataclass, field
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
    purchase_uom: str = "each"
    purchase_pack_qty: int = 1
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
    purchase_uom: str = "each"
    purchase_pack_qty: int = 1
    suggested_department: str | None = None
    product_id: str | None = None
    selected: bool = True
    ai_parsed: bool = False


class CreatePORequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    category_id: str | None = None
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
    purchase_uom: str | None = None
    purchase_pack_qty: int | None = None
    barcode: str | None = None


class ReceiveItemsRequest(BaseModel):
    items: list[ReceiveItemUpdate]


class MarkDeliveryRequest(BaseModel):
    item_ids: list[str]


# ── Read models ────────────────────────────────────────────────────────────────


class POItemRow(BaseModel):
    """Flat read model for a purchase_order_items row (with optional SKU enrichment)."""

    id: str
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
    purchase_uom: str = "each"
    purchase_pack_qty: int = 1
    suggested_department: str = "HDW"
    status: str = "ordered"
    product_id: str | None = None
    organization_id: str = ""
    # Enriched fields — populated by get_po_items when a matched SKU is found
    matched_sku: str | None = None
    matched_name: str | None = None
    matched_quantity: float | None = None
    matched_cost: float | None = None

    model_config = {"extra": "allow"}


class PORow(BaseModel):
    """Flat read model for a purchase_orders row."""

    id: str
    vendor_id: str
    vendor_name: str = ""
    document_date: str | None = None
    total: float | None = None
    status: str = "ordered"
    notes: str | None = None
    created_by_id: str = ""
    created_by_name: str = ""
    received_at: str | None = None
    received_by_id: str | None = None
    received_by_name: str | None = None
    created_at: str = ""
    updated_at: str = ""
    organization_id: str = ""
    xero_bill_id: str | None = None
    xero_sync_status: str | None = None
    # Appended in list endpoints by the API layer
    item_count: int = 0
    ordered_count: int = 0
    pending_count: int = 0
    arrived_count: int = 0

    model_config = {"extra": "allow"}


@dataclass(frozen=True)
class VendorPerformance:
    """Analytics read model for vendor_performance()."""

    vendor_id: str
    vendor_name: str
    days: int
    po_count: int
    total_spend: float
    received_count: int
    avg_lead_time_days: float | None
    fill_rate: float | None


# ── Result models ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreatePOResult:
    """Result of create_purchase_order()."""

    id: str
    vendor_id: str
    vendor_name: str
    vendor_created: bool
    status: str
    item_count: int
    created_at: str


@dataclass(frozen=True)
class MarkDeliveryResult:
    """Result of mark_delivery_received()."""

    po_id: str
    status: str
    transitioned: int


@dataclass(frozen=True)
class ReceiveItemError:
    """A single error from receive_po_items()."""

    item: str | None
    error: str


@dataclass(frozen=True)
class ReceiveItemsResult:
    """Result of receive_po_items()."""

    po_id: str
    status: str
    received: int
    matched: int
    errors: int
    error_details: list[ReceiveItemError] = field(default_factory=list)
    cost_total: float = 0.0
