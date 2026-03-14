"""Cycle count repository — persistence for cycle_counts and cycle_count_items."""

from inventory.domain.cycle_count import CycleCount, CycleCountItem
from shared.infrastructure.database import get_connection, get_org_id


async def insert_count(count: CycleCount) -> None:
    conn = get_connection()
    d = count.model_dump()
    await conn.execute(
        """INSERT INTO cycle_counts
           (id, organization_id, status, scope, created_by_id, created_by_name,
            committed_by_id, committed_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"],
            d["organization_id"],
            d["status"],
            d.get("scope"),
            d["created_by_id"],
            d.get("created_by_name", ""),
            d.get("committed_by_id"),
            d.get("committed_at"),
            d["created_at"],
        ),
    )
    await conn.commit()


async def insert_item(item: CycleCountItem) -> None:
    conn = get_connection()
    d = item.model_dump()
    await conn.execute(
        """INSERT INTO cycle_count_items
           (id, cycle_count_id, product_id, sku, product_name,
            snapshot_qty, counted_qty, variance, unit, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"],
            d["cycle_count_id"],
            d["product_id"],
            d["sku"],
            d.get("product_name", ""),
            d["snapshot_qty"],
            d.get("counted_qty"),
            d.get("variance"),
            d.get("unit", "each"),
            d.get("notes"),
            d["created_at"],
        ),
    )
    await conn.commit()


async def update_item_counted(
    item_id: str,
    counted_qty: float,
    variance: float,
    notes: str | None,
) -> CycleCountItem | None:
    conn = get_connection()
    cursor = await conn.execute(
        """UPDATE cycle_count_items
           SET counted_qty = ?, variance = ?, notes = ?
           WHERE id = ?
           RETURNING *""",
        (counted_qty, variance, notes, item_id),
    )
    row = await cursor.fetchone()
    await conn.commit()
    return CycleCountItem.model_validate(dict(row)) if row else None


async def commit_count(
    count_id: str,
    committed_by_id: str,
    committed_at: str,
) -> bool:
    """Atomically transition status open -> committed. Returns False if already committed."""
    conn = get_connection()
    cursor = await conn.execute(
        """UPDATE cycle_counts
           SET status = 'committed', committed_by_id = ?, committed_at = ?
           WHERE id = ? AND status = 'open'""",
        (committed_by_id, committed_at, count_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def get_count(count_id: str) -> CycleCount | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM cycle_counts WHERE id = ? AND organization_id = ?",
        (count_id, org_id),
    )
    row = await cursor.fetchone()
    return CycleCount.model_validate(dict(row)) if row else None


async def list_counts(status: str | None = None) -> list[CycleCount]:
    conn = get_connection()
    org_id = get_org_id()
    if status:
        cursor = await conn.execute(
            "SELECT * FROM cycle_counts WHERE organization_id = ? AND status = ? ORDER BY created_at DESC",
            (org_id, status),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM cycle_counts WHERE organization_id = ? ORDER BY created_at DESC",
            (org_id,),
        )
    rows = await cursor.fetchall()
    return [CycleCount.model_validate(dict(r)) for r in rows]


async def list_items(cycle_count_id: str) -> list[CycleCountItem]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM cycle_count_items WHERE cycle_count_id = ? ORDER BY sku ASC",
        (cycle_count_id,),
    )
    rows = await cursor.fetchall()
    return [CycleCountItem.model_validate(dict(r)) for r in rows]


async def get_item(item_id: str, cycle_count_id: str) -> CycleCountItem | None:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM cycle_count_items WHERE id = ? AND cycle_count_id = ?",
        (item_id, cycle_count_id),
    )
    row = await cursor.fetchone()
    return CycleCountItem.model_validate(dict(row)) if row else None
