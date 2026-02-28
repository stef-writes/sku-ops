"""Payment transaction repository."""
import json
from typing import Optional

from db import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
    return d


async def insert(payment_dict: dict) -> None:
    conn = get_connection()
    metadata_json = json.dumps(payment_dict.get("metadata", {}))
    await conn.execute(
        """INSERT INTO payment_transactions (id, session_id, withdrawal_id, user_id, contractor_id, amount, currency,
           metadata, payment_status, status, created_at, paid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payment_dict["id"],
            payment_dict["session_id"],
            payment_dict.get("withdrawal_id"),
            payment_dict.get("user_id"),
            payment_dict.get("contractor_id"),
            payment_dict["amount"],
            payment_dict.get("currency", "usd"),
            metadata_json,
            payment_dict.get("payment_status", "pending"),
            payment_dict.get("status", "initiated"),
            payment_dict.get("created_at", ""),
            payment_dict.get("paid_at"),
        ),
    )
    await conn.commit()


async def get_by_session_id(session_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM payment_transactions WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def update_status(session_id: str, payment_status: str, status: str, paid_at: Optional[str] = None) -> None:
    conn = get_connection()
    if paid_at:
        await conn.execute(
            "UPDATE payment_transactions SET payment_status = ?, status = ?, paid_at = ? WHERE session_id = ?",
            (payment_status, status, paid_at, session_id),
        )
    else:
        await conn.execute(
            "UPDATE payment_transactions SET payment_status = ?, status = ? WHERE session_id = ?",
            (payment_status, status, session_id),
        )
    await conn.commit()


class PaymentRepo:
    insert = staticmethod(insert)
    get_by_session_id = staticmethod(get_by_session_id)
    update_status = staticmethod(update_status)


payment_repo = PaymentRepo()
