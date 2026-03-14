"""PO receiving: mark deliveries and receive items into inventory.

Split from purchase_order_service to keep each module under 300 lines.
"""

from datetime import UTC, datetime

from catalog.application.queries import SkuUpdate
from finance.application.ledger_service import record_po_receipt as _record_po_receipt_ledger
from purchasing.application.purchase_order_service import PurchasingDeps, _resolve_po_item_cost
from purchasing.domain.purchase_order import (
    MarkDeliveryResult,
    POItemRow,
    POItemStatus,
    PORow,
    POStatus,
    ReceiveItemError,
    ReceiveItemsResult,
    ReceiveItemUpdate,
)
from purchasing.infrastructure.po_repo import po_repo as _default_repo
from purchasing.ports.po_repo_port import PORepoPort
from shared.infrastructure.database import transaction
from shared.infrastructure.domain_events import dispatch
from shared.kernel.domain_events import InventoryChanged, POItemsReceived
from shared.kernel.errors import ResourceNotFoundError
from shared.kernel.event_payloads import ReceivedItemSummary
from shared.kernel.types import CurrentUser


async def mark_delivery_received(
    po_id: str,
    item_ids: list[str],
    current_user: CurrentUser,  # noqa: ARG001
    repo: PORepoPort = _default_repo,
) -> MarkDeliveryResult:
    """Transition selected 'ordered' items to 'pending' (delivery arrived at dock).

    Does NOT update inventory — that happens on receive_po_items().
    """
    po = await repo.get_po(po_id)
    if not po:
        raise ResourceNotFoundError("PurchaseOrder", po_id)

    all_items = await repo.get_po_items(po_id)
    items_by_id = {i.id: i for i in all_items}

    transitioned = 0
    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if not item or item.status != POItemStatus.ORDERED.value:
            continue
        await repo.update_po_item(item_id, POItemStatus.PENDING)
        transitioned += 1

    return MarkDeliveryResult(po_id=po_id, status=po.status, transitioned=transitioned)


async def receive_po_items(
    po_id: str,
    item_updates: list[ReceiveItemUpdate],
    deps: PurchasingDeps,
    current_user: CurrentUser,
    repo: PORepoPort = _default_repo,
) -> ReceiveItemsResult:
    """Mark selected items as arrived and update inventory stock.

    New SKUs are created for unmatched items; existing SKUs get a
    RECEIVING transaction.
    """
    po = await repo.get_po(po_id)
    if not po:
        raise ResourceNotFoundError("PurchaseOrder", po_id)

    vendor_id: str = po.vendor_id or ""
    departments = await deps.list_departments()
    default_dept = await deps.get_department_by_code("HDW") or (
        departments[0] if departments else None
    )
    dept_by_code = {d.code.upper(): d for d in departments}

    all_items = await repo.get_po_items(po_id)
    items_by_id = {item.id: item for item in all_items}
    updates_by_id = {u.id: u for u in item_updates}

    received = []
    matched = []
    error_details: list[ReceiveItemError] = []
    cost_total = 0.0
    ledger_items: list[ReceivedItemSummary] = []

    async with transaction():
        for item_id, update in updates_by_id.items():
            item = items_by_id.get(item_id)
            if not item:
                error_details.append(ReceiveItemError(item=item_id, error="Item not found"))
                continue

            current_status = POItemStatus(item.status)
            if current_status == POItemStatus.ARRIVED:
                continue
            if current_status == POItemStatus.ORDERED:
                error_details.append(
                    ReceiveItemError(
                        item=item.name, error="Item not yet marked as received at dock"
                    )
                )
                continue

            working = _apply_overrides(item, update)

            delivered = update.delivered_qty
            if delivered is None:
                delivered = working.get("delivered_qty") or working.get("ordered_qty") or 1
            delivered = max(0.0, float(delivered))

            try:
                existing = await _match_sku(working, vendor_id, deps)

                # Transition status FIRST to act as a concurrency guard.
                # The UPDATE uses WHERE status != 'arrived', so only one
                # concurrent request can succeed — the loser gets
                # transitioned=False and skips stock changes.
                resolved_pid = None
                if existing:
                    resolved_pid = existing.id

                    transitioned = await repo.update_po_item(
                        item_id,
                        POItemStatus.ARRIVED,
                        product_id=existing.id,
                        delivered_qty=delivered,
                    )
                    if not transitioned:
                        continue

                    purchase_pack_qty = int(
                        working.get("purchase_pack_qty") or existing.purchase_pack_qty or 1
                    )
                    purchase_uom = (
                        working.get("purchase_uom") or existing.purchase_uom or "each"
                    ).lower()
                    base_unit = (existing.base_unit or "each").lower()
                    stock_qty = _convert_purchase_to_base(
                        delivered, purchase_uom, base_unit, purchase_pack_qty
                    )

                    await deps.process_receiving_stock_changes(
                        product_id=existing.id,
                        sku=existing.sku,
                        product_name=existing.name,
                        quantity=stock_qty,
                        user_id=current_user.id,
                        user_name=current_user.name,
                        reference_id=po_id,
                    )
                    po_item_cost = _resolve_po_item_cost(working)
                    per_base_cost = (
                        po_item_cost / purchase_pack_qty if purchase_pack_qty > 1 else po_item_cost
                    )
                    old_qty = float(existing.quantity)
                    old_cost = float(existing.cost)
                    new_cost: float | None = None
                    if (old_qty + stock_qty) > 0:
                        new_cost = round(
                            (old_qty * old_cost + stock_qty * per_base_cost)
                            / (old_qty + stock_qty),
                            4,
                        )

                    if new_cost is not None:
                        await deps.update_sku(existing.id, SkuUpdate(cost=new_cost))

                    updated = await deps.get_sku_by_id(existing.id)
                    matched.append(updated)
                else:
                    dept = (
                        dept_by_code.get((working.get("suggested_department") or "HDW").upper())
                        or default_dept
                    )
                    if not dept:
                        error_details.append(
                            ReceiveItemError(item=working.get("name"), error="No valid department")
                        )
                        continue

                    cost_val = _resolve_po_item_cost(working)
                    new_sku = await deps.create_product_with_sku(
                        category_id=dept.id,
                        category_name=dept.name,
                        name=working.get("name", "Unknown"),
                        description="",
                        price=float(working.get("unit_price") or working.get("price") or 0),
                        cost=round(cost_val, 2),
                        quantity=delivered,
                        min_stock=5,
                        barcode=working.get("barcode") or None,
                        base_unit=working.get("base_unit") or "each",
                        sell_uom=working.get("sell_uom") or "each",
                        pack_qty=int(working.get("pack_qty") or 1),
                        purchase_uom=working.get("purchase_uom") or "each",
                        purchase_pack_qty=int(working.get("purchase_pack_qty") or 1),
                        user_id=current_user.id,
                        user_name=current_user.name,
                    )
                    resolved_pid = new_sku.id

                    if vendor_id and working.get("original_sku"):
                        await deps.add_vendor_item(
                            sku_id=new_sku.id,
                            vendor_id=vendor_id,
                            vendor_sku=str(working["original_sku"]),
                            purchase_uom=working.get("purchase_uom") or "each",
                            purchase_pack_qty=int(working.get("purchase_pack_qty") or 1),
                            cost=round(cost_val, 2),
                            is_preferred=True,
                        )

                    transitioned = await repo.update_po_item(
                        item_id,
                        POItemStatus.ARRIVED,
                        product_id=new_sku.id,
                        delivered_qty=delivered,
                    )
                    if not transitioned:
                        continue

                    received.append(new_sku)

                item_cost = _resolve_po_item_cost(working)
                cost_total += item_cost * delivered
                dept_code = (working.get("suggested_department") or "HDW").upper()
                ledger_items.append(
                    ReceivedItemSummary(
                        cost=item_cost,
                        delivered_qty=delivered,
                        product_id=resolved_pid,
                        department=dept_by_code[dept_code].name
                        if dept_code in dept_by_code
                        else dept_code,
                    )
                )
            except (ValueError, RuntimeError, OSError, KeyError) as e:
                error_details.append(ReceiveItemError(item=item.name, error=str(e)))

        if ledger_items:
            await _record_po_receipt_ledger(
                po_id=po_id,
                items=ledger_items,
                vendor_name=po.vendor_name,
                performed_by_user_id=current_user.id,
            )

    new_status = await _recompute_po_status(po_id, po, current_user, repo)

    if ledger_items:
        product_ids = tuple(li.product_id for li in ledger_items if li.product_id)
        await dispatch(
            POItemsReceived(
                org_id=current_user.organization_id,
                po_id=po_id,
                vendor_name=po.vendor_name,
                performed_by_user_id=current_user.id,
                items=tuple(ledger_items),
                product_ids=product_ids,
            )
        )
        await dispatch(
            InventoryChanged(
                org_id=current_user.organization_id,
                product_ids=product_ids,
                change_type="receiving",
            )
        )

    return ReceiveItemsResult(
        po_id=po_id,
        status=new_status,
        received=len(received),
        matched=len(matched),
        errors=len(error_details),
        error_details=error_details,
        cost_total=round(cost_total, 2),
    )


# ── Internal helpers ───────────────────────────────────────────────────────────

_DISCRETE_CONTAINER_UOMS = frozenset({"case", "box", "pack", "bag", "roll", "kit"})


def _convert_purchase_to_base(
    delivered: float,
    purchase_uom: str,
    base_unit: str,
    purchase_pack_qty: int,
) -> float:
    """Convert delivered quantity from purchase UOM to base stock units.

    Discrete containers (case, box, etc.) use purchase_pack_qty as the
    multiplier because the generic unit conversion treats them all as 1:1.
    """
    if purchase_uom == base_unit or purchase_pack_qty <= 1:
        return delivered
    if purchase_uom in _DISCRETE_CONTAINER_UOMS:
        return delivered * purchase_pack_qty
    return delivered


_OVERRIDE_FIELDS = (
    "name",
    "cost",
    "unit_price",
    "suggested_department",
    "base_unit",
    "sell_uom",
    "pack_qty",
    "purchase_uom",
    "purchase_pack_qty",
    "barcode",
    "original_sku",
)


def _apply_overrides(item: POItemRow, update: ReceiveItemUpdate) -> dict:
    """Return a mutable working dict of item fields with user overrides applied."""
    working = item.model_dump()
    for field in _OVERRIDE_FIELDS:
        val = getattr(update, field, None)
        if val is not None:
            working[field] = val
    if update.product_id:
        working["product_id"] = update.product_id
    return working


async def _match_sku(item: dict, vendor_id: str, deps: PurchasingDeps):
    """3-tier matching: explicit product_id -> vendor SKU via VendorItem -> name."""
    if item.get("product_id"):
        existing = await deps.get_sku_by_id(item["product_id"])
        if existing:
            return existing
    if item.get("original_sku") and vendor_id:
        vi = await deps.find_vendor_item_by_vendor_and_sku_code(
            vendor_id, str(item["original_sku"]).strip()
        )
        if vi:
            existing = await deps.get_sku_by_id(vi.sku_id)
            if existing:
                return existing
    if item.get("name") and vendor_id:
        existing = await deps.find_sku_by_name_and_vendor(item["name"], vendor_id)
        if existing:
            return existing
    return None


async def _recompute_po_status(
    po_id: str,
    po: PORow,
    current_user: CurrentUser,
    repo: PORepoPort,
) -> str:
    """Recompute PO header status from item statuses.

    ordered  — no items arrived yet
    partial  — some items arrived, some still outstanding
    received — all items arrived
    """
    all_items = await repo.get_po_items(po_id)
    arrived_count = sum(1 for i in all_items if i.status == POItemStatus.ARRIVED.value)
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
        new_status = po.status

    return new_status
