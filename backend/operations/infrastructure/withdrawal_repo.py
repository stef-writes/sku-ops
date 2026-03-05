"""Withdrawal repository."""
import json
from typing import Optional, Union
from uuid import uuid4

from operations.domain.withdrawal import MaterialWithdrawal
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return d


async def insert(withdrawal: Union[MaterialWithdrawal, dict], conn=None) -> None:
    withdrawal_dict = withdrawal if isinstance(withdrawal, dict) else withdrawal.model_dump()
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = withdrawal_dict.get("organization_id") or "default"
    items_json = json.dumps([i if isinstance(i, dict) else i.model_dump() for i in withdrawal_dict["items"]])
    await conn.execute(
        """INSERT INTO withdrawals (id, items, job_id, service_address, notes, subtotal, tax, tax_rate, total, cost_total,
           contractor_id, contractor_name, contractor_company, billing_entity, billing_entity_id, payment_status, invoice_id, paid_at,
           processed_by_id, processed_by_name, organization_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            withdrawal_dict["id"],
            items_json,
            withdrawal_dict["job_id"],
            withdrawal_dict["service_address"],
            withdrawal_dict.get("notes"),
            withdrawal_dict["subtotal"],
            withdrawal_dict["tax"],
            withdrawal_dict.get("tax_rate", 0),
            withdrawal_dict["total"],
            withdrawal_dict["cost_total"],
            withdrawal_dict["contractor_id"],
            withdrawal_dict.get("contractor_name", ""),
            withdrawal_dict.get("contractor_company", ""),
            withdrawal_dict.get("billing_entity", ""),
            withdrawal_dict.get("billing_entity_id"),
            withdrawal_dict.get("payment_status", "unpaid"),
            withdrawal_dict.get("invoice_id"),
            withdrawal_dict.get("paid_at"),
            withdrawal_dict["processed_by_id"],
            withdrawal_dict.get("processed_by_name", ""),
            org_id,
            withdrawal_dict.get("created_at", ""),
        ),
    )
    # Write normalized items
    for item in withdrawal_dict["items"]:
        i = item if isinstance(item, dict) else (item.model_dump() if hasattr(item, "model_dump") else item)
        qty = float(i.get("quantity", 0))
        price = float(i.get("unit_price") or i.get("price") or 0)
        cost = float(i.get("cost", 0))
        await conn.execute(
            """INSERT INTO withdrawal_items
               (id, withdrawal_id, product_id, sku, name, quantity, unit_price, cost, unit, amount, cost_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), withdrawal_dict["id"],
             i.get("product_id", ""), i.get("sku", ""), i.get("name", ""),
             qty, price, cost, i.get("unit", "each"),
             round(qty * price, 2), round(qty * cost, 2)),
        )

    if not in_transaction:
        await conn.commit()


async def list_withdrawals(
    contractor_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10000,
    offset: int = 0,
    organization_id: Optional[str] = None,
) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    query = "SELECT * FROM withdrawals WHERE (organization_id = ? OR organization_id IS NULL)"
    params: list = [org_id]
    if contractor_id:
        query += " AND contractor_id = ?"
        params.append(contractor_id)
    if payment_status:
        query += " AND payment_status = ?"
        params.append(payment_status)
    if billing_entity:
        query += " AND billing_entity = ?"
        params.append(billing_entity)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id(withdrawal_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT * FROM withdrawals WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
            (withdrawal_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM withdrawals WHERE id = ?",
            (withdrawal_id,),
        )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def mark_paid(withdrawal_id: str, paid_at: str) -> Optional[dict]:
    conn = get_connection()
    await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE id = ?",
        (paid_at, withdrawal_id),
    )
    await conn.commit()
    return await get_by_id(withdrawal_id)


async def bulk_mark_paid(withdrawal_ids: list, paid_at: str, organization_id: Optional[str] = None) -> int:
    if not withdrawal_ids:
        return 0
    conn = get_connection()
    org_id = organization_id or "default"
    placeholders = ",".join("?" * len(withdrawal_ids))
    cursor = await conn.execute(
        f"UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE id IN ({placeholders}) AND (organization_id = ? OR organization_id IS NULL)",
        [paid_at] + withdrawal_ids + [org_id],
    )
    await conn.commit()
    return cursor.rowcount


class WithdrawalRepo:
    insert = staticmethod(insert)
    list_withdrawals = staticmethod(list_withdrawals)
    get_by_id = staticmethod(get_by_id)
    mark_paid = staticmethod(mark_paid)
    bulk_mark_paid = staticmethod(bulk_mark_paid)


withdrawal_repo = WithdrawalRepo()
