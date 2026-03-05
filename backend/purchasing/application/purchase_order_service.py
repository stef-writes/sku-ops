"""
Purchase order service: create pending POs and receive items into inventory.

Items are saved as pending when a document is reviewed; inventory only updates
on receive. All types are explicit — no dicts flowing across domain boundaries.
"""
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from dataclasses import dataclass

from kernel.errors import ResourceNotFoundError
from kernel.types import CurrentUser
from catalog.domain.units import ALLOWED_BASE_UNITS
from purchasing.domain.purchase_order import (
    POItemCreate,
    POItemStatus,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from purchasing.infrastructure.po_repo import po_repo as _default_repo
from purchasing.ports.po_repo_port import PORepoPort
from finance.application.ledger_service import record_po_receipt as _record_ledger


@dataclass
class PurchasingDeps:
    """Cross-domain dependencies injected by the API layer."""
    list_departments: Callable[..., Awaitable[list]]
    get_department_by_code: Callable[..., Awaitable[Any]]
    find_vendor_by_name: Callable[..., Awaitable[Any]]
    insert_vendor: Callable[..., Awaitable[None]]
    list_products_by_vendor: Callable[..., Awaitable[list]]
    get_product_by_id: Callable[..., Awaitable[Any]]
    find_product_by_sku_and_vendor: Callable[..., Awaitable[Any]]
    find_product_by_name_and_vendor: Callable[..., Awaitable[Any]]
    update_product: Callable[..., Awaitable[Any]]
    create_product: Callable[..., Awaitable[Any]]
    process_receiving_stock_changes: Callable[..., Awaitable[None]]
    classify_uom_batch: Callable[..., Awaitable[list]]
    infer_uom: Callable[[str], Tuple[str, str, int]]
    suggest_department: Callable[..., Any]
    enrich_for_import: Callable[..., Awaitable[list]]


def _resolve_vendor_dict(vendor_name: str, vendor_id: str) -> dict:
    """Build a minimal vendor insert dict."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": vendor_id,
        "name": vendor_name,
        "contact_name": "",
        "email": "",
        "phone": "",
        "address": "",
        "product_count": 0,
        "created_at": now,
    }


async def create_purchase_order(
    vendor_name: str,
    products: List[POItemCreate],
    deps: PurchasingDeps,
    current_user: CurrentUser,
    document_date: Optional[str] = None,
    total: Optional[float] = None,
    department_id: Optional[str] = None,
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

    org_id = current_user.organization_id

    vendor = await deps.find_vendor_by_name(vendor_name, org_id)
    if not vendor:
        if not create_vendor_if_missing:
            raise ResourceNotFoundError("Vendor", vendor_name)
        from uuid import uuid4
        vendor_id = uuid4().hex
        vendor_dict = _resolve_vendor_dict(vendor_name, vendor_id)
        vendor_dict["organization_id"] = org_id
        await deps.insert_vendor(vendor_dict)
        vendor = {"id": vendor_id, "name": vendor_name}
        vendor_created = True
    else:
        vendor_id = vendor["id"]
        vendor_created = False

    departments = await deps.list_departments()
    dept_by_id = {d["id"]: d for d in departments}
    dept_by_code = {d["code"].upper(): d for d in departments}
    dept_codes = list(dept_by_code.keys())

    override_dept_code = None
    if department_id and department_id in dept_by_id:
        override_dept_code = dept_by_id[department_id]["code"].upper()

    selected = [p for p in products if p.selected]

    # Convert typed DTOs to dicts for enrichment pipeline (enrichment mutates in place)
    selected_dicts = [p.model_dump() for p in selected]

    ai_parsed_items = [d for d in selected_dicts if d.get("ai_parsed")]
    ocr_items = [d for d in selected_dicts if not d.get("ai_parsed")]

    if ocr_items:
        vendor_products = await deps.list_products_by_vendor(vendor_id)
        ocr_items = await deps.enrich_for_import(ocr_items, vendor_products, dept_codes)
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
        d for d in selected_dicts
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

    po_items: List[PurchaseOrderItem] = []
    for item in selected_dicts:
        cost_val = float(item.get("cost") or 0) or float(item.get("price") or 0) * 0.7
        po_items.append(PurchaseOrderItem(
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
        ))

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


async def mark_delivery_received(
    po_id: str,
    item_ids: List[str],
    current_user: CurrentUser,
    repo: PORepoPort = _default_repo,
) -> dict:
    """Transition selected 'ordered' items to 'pending' (delivery arrived at dock).

    Does NOT update inventory — that happens on receive_po_items().
    """
    org_id = current_user.organization_id
    po = await repo.get_po(po_id, org_id)
    if not po:
        raise ResourceNotFoundError("PurchaseOrder", po_id)

    all_items = await repo.get_po_items(po_id)
    items_by_id = {i["id"]: i for i in all_items}

    transitioned = 0
    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if not item or item["status"] != POItemStatus.ORDERED.value:
            continue
        await repo.update_po_item(item_id, POItemStatus.PENDING)
        transitioned += 1

    return {"po_id": po_id, "status": po.get("status", "ordered"), "transitioned": transitioned}


async def receive_po_items(
    po_id: str,
    item_updates: list,
    deps: PurchasingDeps,
    current_user: CurrentUser,
    repo: PORepoPort = _default_repo,
) -> dict:
    """Mark selected items as arrived and update inventory stock.

    New products are created for unmatched items; existing products get a
    RECEIVING transaction.
    """
    org_id = current_user.organization_id
    po = await repo.get_po(po_id, org_id)
    if not po:
        raise ResourceNotFoundError("PurchaseOrder", po_id)

    vendor_id: str = po.get("vendor_id") or ""
    departments = await deps.list_departments()
    default_dept = await deps.get_department_by_code("HDW") or (departments[0] if departments else None)
    dept_by_code = {d["code"].upper(): d for d in departments}

    all_items = await repo.get_po_items(po_id)
    items_by_id = {item["id"]: item for item in all_items}
    updates_by_id = {u["id"]: u for u in item_updates}

    received = []
    matched = []
    errors = []
    cost_total = 0.0
    ledger_items: list[dict] = []

    for item_id, update in updates_by_id.items():
        item = items_by_id.get(item_id)
        if not item:
            errors.append({"item_id": item_id, "error": "Item not found"})
            continue

        current_status = POItemStatus(item["status"])
        if current_status == POItemStatus.ARRIVED:
            continue
        if current_status == POItemStatus.ORDERED:
            errors.append({"item": item.get("name"), "error": "Item not yet marked as received at dock"})
            continue

        delivered = update.get("delivered_qty")
        if delivered is None:
            delivered = item.get("delivered_qty") or item.get("ordered_qty") or 1
        delivered = max(0.0, float(delivered))

        try:
            existing = await _match_product(item, vendor_id, org_id, deps)

            resolved_pid = None
            if existing:
                resolved_pid = existing["id"]
                await deps.process_receiving_stock_changes(
                    product_id=existing["id"],
                    sku=existing["sku"],
                    product_name=existing["name"],
                    quantity=delivered,
                    user_id=current_user.id,
                    user_name=current_user.name,
                    reference_id=po_id,
                    organization_id=org_id,
                )
                product_updates: dict = {}
                if item.get("original_sku") and not existing.get("original_sku"):
                    product_updates["original_sku"] = item["original_sku"]

                po_item_cost = float(item.get("cost") or 0) or float(item.get("unit_price") or item.get("price") or 0) * 0.7
                old_qty = float(existing.get("quantity", 0))
                old_cost = float(existing.get("cost", 0))
                if (old_qty + delivered) > 0:
                    new_cost = round(
                        (old_qty * old_cost + delivered * po_item_cost) / (old_qty + delivered), 4
                    )
                    product_updates["cost"] = new_cost

                if product_updates:
                    await deps.update_product(existing["id"], product_updates)
                await repo.update_po_item(item_id, POItemStatus.ARRIVED, product_id=existing["id"], delivered_qty=delivered)
                updated = await deps.get_product_by_id(existing["id"])
                matched.append(updated)
            else:
                dept = dept_by_code.get((item.get("suggested_department") or "HDW").upper()) or default_dept
                if not dept:
                    errors.append({"item": item.get("name"), "error": "No valid department"})
                    continue

                cost_val = float(item.get("cost") or 0) or float(item.get("unit_price") or item.get("price") or 0) * 0.7
                product = await deps.create_product(
                    department_id=dept["id"],
                    department_name=dept["name"],
                    name=item.get("name", "Unknown"),
                    description="",
                    price=float(item.get("unit_price") or item.get("price") or 0),
                    cost=round(cost_val, 2),
                    quantity=delivered,
                    min_stock=5,
                    vendor_id=vendor_id,
                    vendor_name=po.get("vendor_name", ""),
                    original_sku=item.get("original_sku"),
                    barcode=None,
                    base_unit=item.get("base_unit") or "each",
                    sell_uom=item.get("sell_uom") or "each",
                    pack_qty=int(item.get("pack_qty") or 1),
                    user_id=current_user.id,
                    user_name=current_user.name,
                    organization_id=org_id,
                )
                resolved_pid = product.id
                await repo.update_po_item(item_id, POItemStatus.ARRIVED, product_id=product.id, delivered_qty=delivered)
                received.append(product)

            item_cost = float(item.get("cost") or 0)
            cost_total += item_cost * delivered
            dept_code = (item.get("suggested_department") or "HDW").upper()
            ledger_items.append({
                "cost": item_cost,
                "delivered_qty": delivered,
                "product_id": resolved_pid,
                "department": dept_by_code.get(dept_code, {}).get("name") or dept_code,
            })
        except Exception as e:
            errors.append({"item": item.get("name"), "error": str(e)})

    if ledger_items:
        await _record_ledger(
            po_id=po_id,
            items=ledger_items,
            vendor_name=po.get("vendor_name", ""),
            organization_id=org_id,
        )

    new_status = await _recompute_po_status(po_id, po, current_user, repo)
    return {
        "po_id": po_id,
        "status": new_status,
        "received": len(received),
        "matched": len(matched),
        "errors": len(errors),
        "error_details": errors,
        "cost_total": round(cost_total, 2),
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _match_product(item: dict, vendor_id: str, org_id: str, deps: PurchasingDeps):
    """3-tier matching: explicit product_id → vendor SKU → name."""
    if item.get("product_id"):
        existing = await deps.get_product_by_id(item["product_id"], organization_id=org_id)
        if existing:
            return existing
    if item.get("original_sku") and vendor_id:
        existing = await deps.find_product_by_sku_and_vendor(
            str(item["original_sku"]).strip(), vendor_id, organization_id=org_id
        )
        if existing:
            return existing
    if item.get("name") and vendor_id:
        existing = await deps.find_product_by_name_and_vendor(
            item["name"], vendor_id, organization_id=org_id
        )
        if existing:
            return existing
    return None


async def _recompute_po_status(
    po_id: str,
    po: dict,
    current_user: CurrentUser,
    repo: PORepoPort,
) -> str:
    """Recompute PO header status from item statuses.

    ordered  — no items arrived yet
    partial  — some items arrived, some still outstanding
    received — all items arrived
    """
    all_items = await repo.get_po_items(po_id)
    arrived_count = sum(1 for i in all_items if i["status"] == POItemStatus.ARRIVED.value)
    total = len(all_items)
    now = datetime.now(timezone.utc).isoformat()

    if arrived_count == total and total > 0:
        new_status = POStatus.RECEIVED.value
        await repo.update_po_status(
            po_id, status=new_status,
            received_at=now,
            received_by_id=current_user.id,
            received_by_name=current_user.name,
        )
    elif arrived_count > 0:
        new_status = POStatus.PARTIAL.value
        await repo.update_po_status(po_id, status=new_status)
    else:
        new_status = po.get("status", POStatus.ORDERED.value)

    return new_status
