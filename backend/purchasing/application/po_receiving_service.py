"""PO receiving: mark deliveries and receive items into inventory.

Split from purchase_order_service to keep each module under 300 lines.
"""

from datetime import UTC, datetime

from finance.application.ledger_service import record_po_receipt as _record_ledger
from purchasing.application.purchase_order_service import PurchasingDeps, _resolve_po_item_cost
from purchasing.domain.purchase_order import POItemStatus, POStatus, ReceiveItemUpdate
from purchasing.infrastructure.po_repo import po_repo as _default_repo
from purchasing.ports.po_repo_port import PORepoPort
from shared.kernel.errors import ResourceNotFoundError
from shared.kernel.types import CurrentUser


async def mark_delivery_received(
    po_id: str,
    item_ids: list[str],
    current_user: CurrentUser,  # noqa: ARG001
    repo: PORepoPort = _default_repo,
) -> dict:
    """Transition selected 'ordered' items to 'pending' (delivery arrived at dock).

    Does NOT update inventory — that happens on receive_po_items().
    """
    po = await repo.get_po(po_id)
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
    item_updates: list[ReceiveItemUpdate],
    deps: PurchasingDeps,
    current_user: CurrentUser,
    repo: PORepoPort = _default_repo,
) -> dict:
    """Mark selected items as arrived and update inventory stock.

    New products are created for unmatched items; existing products get a
    RECEIVING transaction.
    """
    po = await repo.get_po(po_id)
    if not po:
        raise ResourceNotFoundError("PurchaseOrder", po_id)

    vendor_id: str = po.get("vendor_id") or ""
    departments = await deps.list_departments()
    default_dept = await deps.get_department_by_code("HDW") or (
        departments[0] if departments else None
    )
    dept_by_code = {d.code.upper(): d for d in departments}

    all_items = await repo.get_po_items(po_id)
    items_by_id = {item["id"]: item for item in all_items}
    updates_by_id = {u.id: u for u in item_updates}

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
            errors.append(
                {"item": item.get("name"), "error": "Item not yet marked as received at dock"}
            )
            continue

        _apply_overrides(item, update)

        delivered = update.delivered_qty
        if delivered is None:
            delivered = item.get("delivered_qty") or item.get("ordered_qty") or 1
        delivered = max(0.0, float(delivered))

        try:
            if update.product_id:
                item["product_id"] = update.product_id

            existing = await _match_product(item, vendor_id, deps)

            resolved_pid = None
            if existing:
                resolved_pid = existing.id
                await deps.process_receiving_stock_changes(
                    product_id=existing.id,
                    sku=existing.sku,
                    product_name=existing.name,
                    quantity=delivered,
                    user_id=current_user.id,
                    user_name=current_user.name,
                    reference_id=po_id,
                )
                product_updates: dict = {}
                if item.get("original_sku") and not existing.original_sku:
                    product_updates["original_sku"] = item["original_sku"]

                po_item_cost = _resolve_po_item_cost(item)
                old_qty = float(existing.quantity)
                old_cost = float(existing.cost)
                if (old_qty + delivered) > 0:
                    new_cost = round(
                        (old_qty * old_cost + delivered * po_item_cost) / (old_qty + delivered), 4
                    )
                    product_updates["cost"] = new_cost

                if product_updates:
                    await deps.update_product(existing.id, product_updates)
                await repo.update_po_item(
                    item_id,
                    POItemStatus.ARRIVED,
                    product_id=existing.id,
                    delivered_qty=delivered,
                )
                updated = await deps.get_product_by_id(existing.id)
                matched.append(updated)
            else:
                dept = (
                    dept_by_code.get((item.get("suggested_department") or "HDW").upper())
                    or default_dept
                )
                if not dept:
                    errors.append({"item": item.get("name"), "error": "No valid department"})
                    continue

                cost_val = _resolve_po_item_cost(item)
                product = await deps.create_product(
                    department_id=dept.id,
                    department_name=dept.name,
                    name=item.get("name", "Unknown"),
                    description="",
                    price=float(item.get("unit_price") or item.get("price") or 0),
                    cost=round(cost_val, 2),
                    quantity=delivered,
                    min_stock=5,
                    vendor_id=vendor_id,
                    vendor_name=po.get("vendor_name", ""),
                    original_sku=item.get("original_sku"),
                    barcode=item.get("barcode") or None,
                    base_unit=item.get("base_unit") or "each",
                    sell_uom=item.get("sell_uom") or "each",
                    pack_qty=int(item.get("pack_qty") or 1),
                    user_id=current_user.id,
                    user_name=current_user.name,
                )
                resolved_pid = product.id
                await repo.update_po_item(
                    item_id, POItemStatus.ARRIVED, product_id=product.id, delivered_qty=delivered
                )
                received.append(product)

            item_cost = _resolve_po_item_cost(item)
            cost_total += item_cost * delivered
            dept_code = (item.get("suggested_department") or "HDW").upper()
            ledger_items.append(
                {
                    "cost": item_cost,
                    "delivered_qty": delivered,
                    "product_id": resolved_pid,
                    "department": dept_by_code[dept_code].name
                    if dept_code in dept_by_code
                    else dept_code,
                }
            )
        except (ValueError, RuntimeError, OSError, KeyError) as e:
            errors.append({"item": item.get("name"), "error": str(e)})

    if ledger_items:
        await _record_ledger(
            po_id=po_id,
            items=ledger_items,
            vendor_name=po.get("vendor_name", ""),
            performed_by_user_id=current_user.id,
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

_OVERRIDE_FIELDS = (
    "name",
    "cost",
    "unit_price",
    "suggested_department",
    "base_unit",
    "sell_uom",
    "pack_qty",
    "barcode",
    "original_sku",
)


def _apply_overrides(item: dict, update: ReceiveItemUpdate) -> None:
    """Merge non-None override fields from the review modal into the PO item dict."""
    for field in _OVERRIDE_FIELDS:
        val = getattr(update, field, None)
        if val is not None:
            item[field] = val


async def _match_product(item: dict, vendor_id: str, deps: PurchasingDeps):
    """3-tier matching: explicit product_id -> vendor SKU -> name."""
    if item.get("product_id"):
        existing = await deps.get_product_by_id(item["product_id"])
        if existing:
            return existing
    if item.get("original_sku") and vendor_id:
        existing = await deps.find_product_by_sku_and_vendor(
            str(item["original_sku"]).strip(), vendor_id
        )
        if existing:
            return existing
    if item.get("name") and vendor_id:
        existing = await deps.find_product_by_name_and_vendor(item["name"], vendor_id)
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
    now = datetime.now(UTC).isoformat()

    if arrived_count == total and total > 0:
        new_status = POStatus.RECEIVED.value
        await repo.update_po_status(
            po_id,
            status=new_status,
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
