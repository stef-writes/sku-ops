"""
Purchase order service: create pending POs and receive items into inventory.

Items are saved as pending when a document is reviewed; inventory only updates
on receive. All types are explicit — no dicts flowing across domain boundaries.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from purchasing.domain.purchase_order import (
    POItemCreate,
    POItemStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from purchasing.infrastructure.po_repo import po_repo as _default_repo
from purchasing.ports.po_repo_port import PORepoPort
from shared.infrastructure.db import get_org_id
from shared.kernel.errors import ResourceNotFoundError
from shared.kernel.types import CurrentUser
from shared.kernel.units import ALLOWED_BASE_UNITS


@dataclass
class PurchasingDeps:
    """Cross-domain dependencies injected by the API layer."""

    list_departments: Callable[..., Awaitable[list]]
    get_department_by_code: Callable[..., Awaitable[Any]]
    find_vendor_by_name: Callable[..., Awaitable[Any]]
    insert_vendor: Callable[..., Awaitable[None]]
    get_sku_by_id: Callable[..., Awaitable[Any]]
    find_vendor_item_by_vendor_and_sku_code: Callable[..., Awaitable[Any]]
    find_sku_by_name_and_vendor: Callable[..., Awaitable[Any]]
    update_sku: Callable[..., Awaitable[Any]]
    create_product_with_sku: Callable[..., Awaitable[Any]]
    add_vendor_item: Callable[..., Awaitable[Any]]
    process_receiving_stock_changes: Callable[..., Awaitable[None]]
    classify_uom_batch: Callable[..., Awaitable[list]]
    infer_uom: Callable[[str], tuple[str, str, int]]
    suggest_department: Callable[..., Any]
    enrich_for_import: Callable[..., Awaitable[list]]


def _resolve_vendor_dict(vendor_name: str, vendor_id: str) -> dict:
    """Build a minimal vendor insert dict."""
    now = datetime.now(UTC).isoformat()
    return {
        "id": vendor_id,
        "name": vendor_name,
        "contact_name": "",
        "email": "",
        "phone": "",
        "address": "",
        "created_at": now,
    }


def _resolve_po_item_cost(item: dict) -> float:
    """Derive item cost from cost field, falling back to 70% of unit_price/price."""
    cost = float(item.get("cost") or 0)
    if cost == 0:
        price = float(item.get("unit_price") or item.get("price") or 0)
        cost = round(price * 0.7, 4) if price else 0
    return cost


async def create_purchase_order(
    vendor_name: str,
    products: list[POItemCreate],
    deps: PurchasingDeps,
    current_user: CurrentUser,
    document_date: str | None = None,
    total: float | None = None,
    category_id: str | None = None,
    create_vendor_if_missing: bool = True,
    repo: PORepoPort = _default_repo,
) -> dict:
    """Save reviewed receipt items as a pending purchase order.

    Runs enrichment (UOM inference, dept suggestion, LLM) but does NOT update
    inventory — that happens on receive.
    """
    vendor_name = (vendor_name or "").strip()
    if not vendor_name:
        raise ValueError("Vendor name is required")

    org_id = get_org_id()

    vendor = await deps.find_vendor_by_name(vendor_name)
    if not vendor:
        if not create_vendor_if_missing:
            raise ResourceNotFoundError("Vendor", vendor_name)
        vendor_id = uuid4().hex
        vendor_dict = _resolve_vendor_dict(vendor_name, vendor_id)
        vendor_dict["organization_id"] = org_id
        await deps.insert_vendor(vendor_dict)
        vendor_created = True
    else:
        vendor_id = vendor.id
        vendor_name = vendor.name
        vendor_created = False

    departments = await deps.list_departments()
    dept_by_id = {d.id: d for d in departments}
    dept_by_code = {d.code.upper(): d for d in departments}
    dept_codes = list(dept_by_code.keys())

    override_dept_code = None
    if category_id and category_id in dept_by_id:
        override_dept_code = dept_by_id[category_id].code.upper()

    selected = [p for p in products if p.selected]

    selected_dicts = [p.model_dump() for p in selected]

    ai_parsed_items = [d for d in selected_dicts if d.get("ai_parsed")]
    ocr_items = [d for d in selected_dicts if not d.get("ai_parsed")]

    if ocr_items:
        ocr_items = await deps.enrich_for_import(ocr_items, [], dept_codes)
    for item in selected_dicts:
        item.pop("enrichment_warning", None)

    selected_dicts = ai_parsed_items + ocr_items

    for item in selected_dicts:
        if override_dept_code:
            item["suggested_department"] = override_dept_code
        else:
            suggested = (item.get("suggested_department") or "HDW").upper()
            if not suggested or suggested == "HDW" or suggested not in dept_by_code:
                rule_dept = deps.suggest_department(item.get("name", "") or "", dept_by_code)
                if rule_dept:
                    item["suggested_department"] = rule_dept

    for item in selected_dicts:
        bu = (item.get("base_unit") or "each").lower()
        su = (item.get("sell_uom") or "each").lower()
        if bu == "each" and su == "each":
            inferred_bu, inferred_su, inferred_pq = deps.infer_uom(item.get("name", "") or "")
            if inferred_bu != "each":
                item["base_unit"] = inferred_bu
                item["sell_uom"] = inferred_su
                item["pack_qty"] = inferred_pq

    needs_uom = [
        d
        for d in selected_dicts
        if (
            (d.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS
            or (d.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS
            or (
                (d.get("base_unit") or "each").lower() == "each"
                and (d.get("sell_uom") or "each").lower() == "each"
            )
        )
    ]
    if needs_uom:
        await deps.classify_uom_batch(needs_uom)

    po = PurchaseOrder(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        document_date=document_date,
        total=total,
        status=POStatus.ORDERED,
        created_by_id=current_user.id,
        created_by_name=current_user.name,
        organization_id=org_id,
    )

    po_items: list[PurchaseOrderItem] = []
    for item in selected_dicts:
        cost_val = _resolve_po_item_cost(item)
        po_items.append(
            PurchaseOrderItem(
                po_id=po.id,
                name=item.get("name", "Unknown"),
                original_sku=item.get("original_sku"),
                ordered_qty=float(item.get("ordered_qty") or item.get("quantity") or 1),
                delivered_qty=item.get("delivered_qty") or 0,
                unit_price=float(item.get("price") or 0),
                cost=round(cost_val, 2),
                base_unit=item.get("base_unit") or "each",
                sell_uom=item.get("sell_uom") or "each",
                pack_qty=int(item.get("pack_qty") or 1),
                suggested_department=(item.get("suggested_department") or "HDW").upper(),
                status=POItemStatus.ORDERED,
                product_id=item.get("product_id") or None,
                organization_id=org_id,
            )
        )

    await repo.insert_po(po)
    await repo.insert_items(po_items)

    return {
        "id": po.id,
        "vendor_id": vendor_id,
        "vendor_created": vendor_created,
        "vendor_name": vendor_name,
        "status": po.status.value,
        "item_count": len(po_items),
        "created_at": po.created_at,
    }


# Re-export receiving functions so existing imports from this module keep working
from purchasing.application.po_receiving_service import (  # noqa: E402
    _apply_overrides,
    _match_sku,
    _recompute_po_status,
    mark_delivery_received,
    receive_po_items,
)

__all__ = [
    "PurchasingDeps",
    "_apply_overrides",
    "_match_sku",
    "_recompute_po_status",
    "_resolve_po_item_cost",
    "_resolve_vendor_dict",
    "create_purchase_order",
    "mark_delivery_received",
    "receive_po_items",
]
