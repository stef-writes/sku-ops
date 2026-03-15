"""Inventory application queries — safe for cross-context import.

Exposes stock transaction analytics without leaking infrastructure details.
"""

from shared.infrastructure.database import get_connection, get_org_id


async def withdrawal_velocity(
    product_ids: list[str],
    since: str,
) -> dict[str, float]:
    """Total units withdrawn per product since a date. Keyed by product_id."""
    if not product_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join(f"${i}" for i in range(1, len(product_ids) + 1))
    since_idx = len(product_ids) + 1
    cur = await conn.execute(
        "SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used"
        " FROM stock_transactions"
        " WHERE product_id IN ("
        + placeholders
        + f") AND transaction_type = 'WITHDRAWAL' AND created_at >= ${since_idx}"
        " GROUP BY product_id",
        (*product_ids, since),
    )
    return {row["product_id"]: row["total_used"] for row in await cur.fetchall()}


async def daily_withdrawal_activity(
    since: str,
    product_id: str | None = None,
) -> list[dict]:
    """Daily withdrawal activity: transaction_count + units_moved per day."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [org_id, since]
    product_filter = ""
    if product_id:
        product_filter = " AND product_id = $3"
        params.append(product_id)

    cur = await conn.execute(
        "SELECT DATE(created_at) AS day,"
        " COUNT(*) AS transaction_count,"
        " COALESCE(SUM(ABS(quantity_delta)), 0) AS units_moved"
        " FROM stock_transactions"
        " WHERE (organization_id = $1 OR organization_id IS NULL)"
        " AND transaction_type = 'WITHDRAWAL'"
        " AND created_at >= $2" + product_filter + " GROUP BY day"
        " ORDER BY day",
        params,
    )
    return [dict(r) for r in await cur.fetchall()]
