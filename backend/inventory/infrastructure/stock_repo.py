"""Stock transaction repository."""

from inventory.domain.stock import StockTransaction
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> StockTransaction | None:
    if row is None:
        return None
    return StockTransaction.model_validate(dict(row))


async def insert_transaction(tx: StockTransaction) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO stock_transactions (id, product_id, sku, product_name, quantity_delta, quantity_before,
           quantity_after, unit, transaction_type, reference_id, reference_type, reason, user_id, user_name, organization_id, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)""",
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
            tx.organization_id,
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
           WHERE product_id = $1 AND organization_id = $2
           ORDER BY created_at DESC LIMIT $3""",
        (product_id, org_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


class StockRepo:
    insert_transaction = staticmethod(insert_transaction)
    list_by_product = staticmethod(list_by_product)


stock_repo = StockRepo()
