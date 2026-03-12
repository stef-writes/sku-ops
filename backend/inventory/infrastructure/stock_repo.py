"""Stock transaction repository."""

from inventory.domain.stock import StockTransaction
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> StockTransaction | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return StockTransaction.model_validate(d)


async def insert_transaction(transaction: StockTransaction | dict) -> None:
    tx_dict = transaction if isinstance(transaction, dict) else transaction.model_dump()
    conn = get_connection()
    org_id = tx_dict.get("organization_id") or get_org_id()
    await conn.execute(
        """INSERT INTO stock_transactions (id, product_id, sku, product_name, quantity_delta, quantity_before,
           quantity_after, unit, transaction_type, reference_id, reference_type, reason, user_id, user_name, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tx_dict["id"],
            tx_dict["product_id"],
            tx_dict["sku"],
            tx_dict.get("product_name", ""),
            tx_dict["quantity_delta"],
            tx_dict["quantity_before"],
            tx_dict["quantity_after"],
            tx_dict.get("unit", "each"),
            tx_dict["transaction_type"].value
            if hasattr(tx_dict["transaction_type"], "value")
            else tx_dict["transaction_type"],
            tx_dict.get("reference_id"),
            tx_dict.get("reference_type"),
            tx_dict.get("reason"),
            tx_dict["user_id"],
            tx_dict.get("user_name", ""),
            org_id,
            tx_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def list_by_product(
    product_id: str,
    limit: int = 50,
) -> list[StockTransaction]:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [product_id]
    where = "WHERE product_id = ?"
    where += " AND (organization_id = ? OR organization_id IS NULL)"
    params.append(org_id)
    params.append(limit)
    cursor = await conn.execute(
        "SELECT * FROM stock_transactions " + where + " ORDER BY created_at DESC LIMIT ?",
        params,
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


class StockRepo:
    insert_transaction = staticmethod(insert_transaction)
    list_by_product = staticmethod(list_by_product)


stock_repo = StockRepo()
