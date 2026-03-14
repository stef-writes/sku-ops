"""Stock transaction repository."""

from inventory.domain.stock import StockTransaction
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> StockTransaction | None:
    if row is None:
        return None
    d = dict(row)
    d.pop("organization_id", None)
    return StockTransaction.model_validate(d)


async def insert_transaction(tx: StockTransaction) -> None:
    conn = get_connection()
    org_id = tx.organization_id or get_org_id()
    await conn.execute(
        """INSERT INTO stock_transactions (id, product_id, sku, product_name, quantity_delta, quantity_before,
           quantity_after, unit, transaction_type, reference_id, reference_type, reason, user_id, user_name, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tx.id,
            tx.product_id,
            tx.sku,
            tx.product_name,
            tx.quantity_delta,
            tx.quantity_before,
            tx.quantity_after,
            tx.unit,
            tx.transaction_type.value,
            tx.reference_id,
            tx.reference_type,
            tx.reason,
            tx.user_id,
            tx.user_name,
            org_id,
            tx.created_at,
        ),
    )
    await conn.commit()


async def list_by_product(
    product_id: str,
    limit: int = 50,
) -> list[StockTransaction]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT * FROM stock_transactions
           WHERE product_id = ? AND (organization_id = ? OR organization_id IS NULL)
           ORDER BY created_at DESC LIMIT ?""",
        (product_id, org_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


class StockRepo:
    insert_transaction = staticmethod(insert_transaction)
    list_by_product = staticmethod(list_by_product)


stock_repo = StockRepo()
