"""Cycle count application service.

Lifecycle:
  open  → counters enter counted_qty line by line
        → get_count_detail for live variance preview
  commit → applies all non-zero variances as stock adjustments inside a single
           database transaction (all-or-nothing), then transitions status to
           committed in the same transaction.

The snapshot (snapshot_qty) is frozen at open time and never changed.
Inventory is only touched at commit — never during the counting phase.
"""

from datetime import UTC, datetime

from catalog.application.queries import list_products
from inventory.application.inventory_service import process_adjustment_stock_changes
from inventory.domain.cycle_count import CycleCount, CycleCountItem, CycleCountStatus
from inventory.infrastructure import cycle_count_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.errors import ResourceNotFoundError


async def open_cycle_count(
    created_by_id: str,
    created_by_name: str,
    scope: str | None = None,
) -> dict:
    """Open a new cycle count session.

    Snapshots the current quantity of every active product in scope.
    scope=None counts everything; scope=<department_name> limits to that dept.
    Returns the serialized CycleCount.
    """
    products = await list_products()
    if scope:
        products = [p for p in products if p.department_name == scope]

    if not products:
        raise ValueError(
            f"No products found{f' in department {scope!r}' if scope else ''}. "
            "Cannot open an empty cycle count."
        )

    count = CycleCount(
        organization_id=get_org_id(),
        scope=scope,
        created_by_id=created_by_id,
        created_by_name=created_by_name,
    )
    await cycle_count_repo.insert_count(count)

    for p in products:
        item = CycleCountItem(
            cycle_count_id=count.id,
            product_id=p.id,
            sku=p.sku,
            product_name=p.name,
            snapshot_qty=float(p.quantity),
            unit=p.base_unit or "each",
        )
        await cycle_count_repo.insert_item(item)

    return count.model_dump()


async def update_counted_qty(
    count_id: str,
    item_id: str,
    counted_qty: float,
    notes: str | None,
) -> dict:
    """Record the physical count for one line item.

    Computes variance = counted_qty - snapshot_qty inline.
    The count must still be open.
    """
    count = await cycle_count_repo.get_count(count_id)
    if not count:
        raise ResourceNotFoundError("CycleCount", count_id)
    if count["status"] != CycleCountStatus.OPEN:
        raise ValueError("Cannot update a committed cycle count.")

    item = await cycle_count_repo.get_item(item_id, count_id)
    if not item:
        raise ResourceNotFoundError("CycleCountItem", item_id)

    variance = round(counted_qty - float(item["snapshot_qty"]), 6)
    updated = await cycle_count_repo.update_item_counted(
        item_id=item_id,
        counted_qty=counted_qty,
        variance=variance,
        notes=notes,
    )
    if not updated:
        raise ResourceNotFoundError("CycleCountItem", item_id)
    return updated


async def get_count_detail(count_id: str) -> dict:
    """Return the count header plus all line items with their current variance."""
    count = await cycle_count_repo.get_count(count_id)
    if not count:
        raise ResourceNotFoundError("CycleCount", count_id)

    items = await cycle_count_repo.list_items(count_id)
    return {**count, "items": items}


async def commit_cycle_count(
    count_id: str,
    committed_by_id: str,
    committed_by_name: str,
) -> dict:
    """Apply all non-zero variances as stock adjustments and close the count.

    All adjustments and the status transition run inside a single database
    transaction. If any adjustment fails (e.g. NegativeStockError), the entire
    commit is rolled back — no partial state is ever written.

    Items without a counted_qty are skipped (uncounted = no adjustment).
    Items with variance == 0 are skipped (no change needed).
    """
    count = await cycle_count_repo.get_count(count_id)
    if not count:
        raise ResourceNotFoundError("CycleCount", count_id)
    if count["status"] != CycleCountStatus.OPEN:
        raise ValueError("Cycle count is already committed.")

    items = await cycle_count_repo.list_items(count_id)
    items_to_adjust = [
        i
        for i in items
        if i.get("counted_qty") is not None and i.get("variance") not in (None, 0, 0.0)
    ]

    committed_at = datetime.now(UTC).isoformat()

    async with transaction():
        for item in items_to_adjust:
            await process_adjustment_stock_changes(
                product_id=item["product_id"],
                quantity_delta=float(item["variance"]),
                reason="count",
                user_id=committed_by_id,
                user_name=committed_by_name,
            )
        await cycle_count_repo.commit_count(
            count_id=count_id,
            committed_by_id=committed_by_id,
            committed_at=committed_at,
        )

    count["status"] = CycleCountStatus.COMMITTED
    count["committed_by_id"] = committed_by_id
    count["committed_at"] = committed_at
    count["items_adjusted"] = len(items_to_adjust)
    return count


async def list_cycle_counts(status: str | None = None) -> list:
    return await cycle_count_repo.list_counts(status=status)
