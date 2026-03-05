"""Payment repository — persistence for payment records."""
from typing import Optional, Union

from finance.domain.payment import Payment
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else {}


_COLUMNS = "id, invoice_id, billing_entity_id, amount, method, reference, payment_date, notes, recorded_by_id, xero_payment_id, organization_id, created_at, updated_at"


async def insert(payment: Union[Payment, dict], withdrawal_ids: list[str] | None = None, conn=None) -> None:
    d = payment if isinstance(payment, dict) else payment.model_dump()
    in_tx = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        f"""INSERT INTO payments ({_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d["id"], d.get("invoice_id"), d.get("billing_entity_id"),
            d["amount"], d.get("method", "bank_transfer"), d.get("reference", ""),
            d["payment_date"], d.get("notes"),
            d["recorded_by_id"], d.get("xero_payment_id"),
            d["organization_id"], d["created_at"], d["updated_at"],
        ),
    )
    for wid in (withdrawal_ids or []):
        await conn.execute(
            "INSERT INTO payment_withdrawals (payment_id, withdrawal_id) VALUES (?, ?)",
            (d["id"], wid),
        )
    if not in_tx:
        await conn.commit()


async def get_by_id(payment_id: str, organization_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM payments WHERE id = ? AND organization_id = ?",
        (payment_id, organization_id),
    )
    p = _row_to_dict(await cursor.fetchone())
    if p:
        wc = await conn.execute(
            "SELECT withdrawal_id FROM payment_withdrawals WHERE payment_id = ?",
            (payment_id,),
        )
        p["withdrawal_ids"] = [
            (r[0] if isinstance(r, (tuple, list)) else r.get("withdrawal_id"))
            for r in await wc.fetchall()
        ]
    return p


async def list_payments(
    organization_id: str,
    invoice_id: Optional[str] = None,
    billing_entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    conn = get_connection()
    sql = f"SELECT {_COLUMNS} FROM payments WHERE organization_id = ?"
    params: list = [organization_id]
    if invoice_id:
        sql += " AND invoice_id = ?"
        params.append(invoice_id)
    if billing_entity_id:
        sql += " AND billing_entity_id = ?"
        params.append(billing_entity_id)
    if start_date:
        sql += " AND payment_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND payment_date <= ?"
        params.append(end_date)
    sql += " ORDER BY payment_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(sql, params)
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def list_for_invoice(invoice_id: str, organization_id: str) -> list:
    conn = get_connection()
    cursor = await conn.execute(
        f"SELECT {_COLUMNS} FROM payments WHERE invoice_id = ? AND organization_id = ? ORDER BY payment_date DESC",
        (invoice_id, organization_id),
    )
    return [_row_to_dict(r) for r in await cursor.fetchall()]


async def list_for_withdrawal(withdrawal_id: str, organization_id: str) -> list:
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT p.* FROM payments p
           JOIN payment_withdrawals pw ON pw.payment_id = p.id
           WHERE pw.withdrawal_id = ? AND p.organization_id = ?
           ORDER BY p.payment_date DESC""",
        (withdrawal_id, organization_id),
    )
    return [_row_to_dict(r) for r in await cursor.fetchall()]


class PaymentRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_payments = staticmethod(list_payments)
    list_for_invoice = staticmethod(list_for_invoice)
    list_for_withdrawal = staticmethod(list_for_withdrawal)


payment_repo = PaymentRepo()
