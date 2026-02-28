"""Stock transaction repository."""
from typing import Optional

from db import get_connection


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


async def insert_transaction(tx_dict: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO stock_transactions (id, product_id, sku, product_name, quantity_delta, quantity_before,
           quantity_after, transaction_type, reference_id, reference_type, reason, user_id, user_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tx_dict["id"],
            tx_dict["product_id"],
            tx_dict["sku"],
            tx_dict.get("product_name", ""),
            tx_dict["quantity_delta"],
            tx_dict["quantity_before"],
            tx_dict["quantity_after"],
            tx_dict["transaction_type"].value if hasattr(tx_dict["transaction_type"], "value") else tx_dict["transaction_type"],
            tx_dict.get("reference_id"),
            tx_dict.get("reference_type"),
            tx_dict.get("reason"),
            tx_dict["user_id"],
            tx_dict.get("user_name", ""),
            tx_dict.get("created_at", ""),
        ),
    )
    await conn.commit()


async def list_by_product(product_id: str, limit: int = 50) -> list:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM stock_transactions WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
        (product_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


class StockRepo:
    insert_transaction = staticmethod(insert_transaction)
    list_by_product = staticmethod(list_by_product)


stock_repo = StockRepo()
