"""Withdrawal repository."""

import json
from uuid import uuid4

from operations.domain.withdrawal import MaterialWithdrawal
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> MaterialWithdrawal | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return MaterialWithdrawal.model_validate(d)


async def insert(withdrawal: MaterialWithdrawal | dict) -> None:
    withdrawal_dict = withdrawal if isinstance(withdrawal, dict) else withdrawal.model_dump()
    conn = get_connection()
    org_id = withdrawal_dict.get("organization_id") or get_org_id()
    items_json = json.dumps(
        [i if isinstance(i, dict) else i.model_dump() for i in withdrawal_dict["items"]]
    )
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
        i = (
            item
            if isinstance(item, dict)
            else (item.model_dump() if hasattr(item, "model_dump") else item)
        )
        qty = float(i.get("quantity", 0))
        price = float(i.get("unit_price") or i.get("price") or 0)
        cost = float(i.get("cost", 0))
        await conn.execute(
            """INSERT INTO withdrawal_items
               (id, withdrawal_id, product_id, sku, name, quantity, unit_price, cost, unit, amount, cost_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                withdrawal_dict["id"],
                i.get("product_id", ""),
                i.get("sku", ""),
                i.get("name", ""),
                qty,
                price,
                cost,
                i.get("unit", "each"),
                round(qty * price, 2),
                round(qty * cost, 2),
            ),
        )

    await conn.commit()


async def list_withdrawals(
    contractor_id: str | None = None,
    payment_status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10000,
    offset: int = 0,
) -> list[MaterialWithdrawal]:
    conn = get_connection()
    org_id = get_org_id()
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
    return [_row_to_model(r) for r in rows]


async def get_by_id(withdrawal_id: str) -> MaterialWithdrawal | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM withdrawals WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
        (withdrawal_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def mark_paid(withdrawal_id: str, paid_at: str) -> MaterialWithdrawal | None:
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE id = ? AND organization_id = ?",
        (paid_at, withdrawal_id, org_id),
    )
    await conn.commit()
    return await get_by_id(withdrawal_id)


async def bulk_mark_paid(withdrawal_ids: list, paid_at: str) -> int:
    if not withdrawal_ids:
        return 0
    conn = get_connection()
    org_id = get_org_id()
    placeholders = ",".join("?" * len(withdrawal_ids))
    cursor = await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE id IN ("
        + placeholders
        + ") AND (organization_id = ? OR organization_id IS NULL)",
        [paid_at, *withdrawal_ids, org_id],
    )
    await conn.commit()
    return cursor.rowcount


async def link_to_invoice(withdrawal_id: str, invoice_id: str) -> None:
    """Set invoice_id and mark as invoiced. Called by finance context via facade."""
    conn = get_connection()
    await conn.execute(
        "UPDATE withdrawals SET invoice_id = ?, payment_status = 'invoiced' WHERE id = ?",
        (invoice_id, withdrawal_id),
    )
    await conn.commit()


async def unlink_from_invoice(withdrawal_ids: list[str]) -> None:
    """Clear invoice link and reset to unpaid. Called by finance context via facade."""
    if not withdrawal_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" * len(withdrawal_ids))
    await conn.execute(
        f"UPDATE withdrawals SET invoice_id = NULL, payment_status = 'unpaid' WHERE id IN ({placeholders})",
        withdrawal_ids,
    )
    await conn.commit()


async def mark_paid_by_invoice(invoice_id: str, paid_at: str) -> None:
    """Mark all withdrawals linked to an invoice as paid. Called by finance context via facade."""
    conn = get_connection()
    await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE invoice_id = ?",
        (paid_at, invoice_id),
    )
    await conn.commit()


async def units_sold_by_product(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    """Sum of quantities sold per product_id from withdrawal_items."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND w.created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND w.created_at <= ?"
        params.append(end_date)
    query = (
        "SELECT wi.product_id, SUM(wi.quantity) AS total_qty"
        " FROM withdrawal_items wi"
        " JOIN withdrawals w ON wi.withdrawal_id = w.id"
        " WHERE w.organization_id = ?"
    )
    query += date_filter
    query += " GROUP BY wi.product_id"
    cursor = await conn.execute(query, params)
    return {row[0]: row[1] for row in await cursor.fetchall()}


async def payment_status_breakdown(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    """Revenue breakdown by payment status: {Paid: X, Invoiced: Y, Unpaid: Z}."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND w.created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND w.created_at <= ?"
        params.append(end_date)
    query = (
        "SELECT"
        " CASE"
        " WHEN w.payment_status = 'paid' THEN 'Paid'"
        " WHEN w.invoice_id IS NOT NULL THEN 'Invoiced'"
        " ELSE 'Unpaid'"
        " END AS status,"
        " ROUND(CAST(SUM(w.total) AS NUMERIC), 2) AS total"
        " FROM withdrawals w"
        " WHERE w.organization_id = ?"
    )
    query += date_filter
    query += " GROUP BY status"
    cursor = await conn.execute(query, params)
    return {row[0]: row[1] for row in await cursor.fetchall()}


class WithdrawalRepo:
    insert = staticmethod(insert)
    list_withdrawals = staticmethod(list_withdrawals)
    get_by_id = staticmethod(get_by_id)
    mark_paid = staticmethod(mark_paid)
    bulk_mark_paid = staticmethod(bulk_mark_paid)
    link_to_invoice = staticmethod(link_to_invoice)
    unlink_from_invoice = staticmethod(unlink_from_invoice)
    mark_paid_by_invoice = staticmethod(mark_paid_by_invoice)
    units_sold_by_product = staticmethod(units_sold_by_product)
    payment_status_breakdown = staticmethod(payment_status_breakdown)


withdrawal_repo = WithdrawalRepo()
