"""Withdrawal repository."""

import json
from uuid import uuid4

from operations.domain.withdrawal import MaterialWithdrawal
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> MaterialWithdrawal | None:
    if row is None:
        return None
    d = dict(row)
    if d and "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return MaterialWithdrawal.model_validate(d)


async def insert(withdrawal: MaterialWithdrawal) -> None:
    conn = get_connection()
    org_id = withdrawal.organization_id or get_org_id()
    items_json = json.dumps([i.model_dump() for i in withdrawal.items])
    await conn.execute(
        """INSERT INTO withdrawals (id, items, job_id, service_address, notes, subtotal, tax, tax_rate, total, cost_total,
           contractor_id, contractor_name, contractor_company, billing_entity, billing_entity_id, payment_status, invoice_id, paid_at,
           processed_by_id, processed_by_name, organization_id, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)""",
        (
            withdrawal.id,
            items_json,
            withdrawal.job_id,
            withdrawal.service_address,
            withdrawal.notes,
            withdrawal.subtotal,
            withdrawal.tax,
            withdrawal.tax_rate,
            withdrawal.total,
            withdrawal.cost_total,
            withdrawal.contractor_id,
            withdrawal.contractor_name,
            withdrawal.contractor_company,
            withdrawal.billing_entity,
            withdrawal.billing_entity_id,
            withdrawal.payment_status,
            withdrawal.invoice_id,
            withdrawal.paid_at,
            withdrawal.processed_by_id,
            withdrawal.processed_by_name,
            org_id,
            withdrawal.created_at,
        ),
    )
    for item in withdrawal.items:
        qty = float(item.quantity)
        price = float(item.unit_price)
        cost = float(item.cost)
        await conn.execute(
            """INSERT INTO withdrawal_items
               (id, withdrawal_id, product_id, sku, name, quantity, unit_price, cost, unit, amount, cost_total)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
            (
                str(uuid4()),
                withdrawal.id,
                item.product_id or "",
                item.sku or "",
                item.name or "",
                qty,
                price,
                cost,
                item.unit or "each",
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
    n = 1
    query = f"SELECT * FROM withdrawals WHERE (organization_id = ${n} OR organization_id IS NULL)"
    params: list = [org_id]
    n += 1
    if contractor_id:
        query += f" AND contractor_id = ${n}"
        params.append(contractor_id)
        n += 1
    if payment_status:
        query += f" AND payment_status = ${n}"
        params.append(payment_status)
        n += 1
    if billing_entity:
        query += f" AND billing_entity = ${n}"
        params.append(billing_entity)
        n += 1
    if start_date:
        query += f" AND created_at >= ${n}"
        params.append(start_date)
        n += 1
    if end_date:
        query += f" AND created_at <= ${n}"
        params.append(end_date)
        n += 1
    query += f" ORDER BY created_at DESC LIMIT ${n} OFFSET ${n + 1}"
    params.extend([limit, offset])
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def get_by_id(withdrawal_id: str) -> MaterialWithdrawal | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM withdrawals WHERE id = $1 AND (organization_id = $2 OR organization_id IS NULL)",
        (withdrawal_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def mark_paid(withdrawal_id: str, paid_at: str) -> tuple[MaterialWithdrawal | None, bool]:
    """Mark withdrawal paid. Returns (withdrawal, actually_changed)."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = $1 "
        "WHERE id = $2 AND payment_status != 'paid' AND organization_id = $3",
        (paid_at, withdrawal_id, org_id),
    )
    await conn.commit()
    return await get_by_id(withdrawal_id), cursor.rowcount > 0


async def bulk_mark_paid(withdrawal_ids: list[str], paid_at: str) -> list[str]:
    """Mark withdrawals paid. Returns IDs that were actually changed (previously unpaid)."""
    if not withdrawal_ids:
        return []
    conn = get_connection()
    org_id = get_org_id()
    placeholders = ",".join(f"${i}" for i in range(2, 2 + len(withdrawal_ids)))
    cursor = await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = $1 WHERE id IN ("
        + placeholders
        + ") AND payment_status != 'paid'"
        f" AND (organization_id = ${2 + len(withdrawal_ids)} OR organization_id IS NULL) RETURNING id",
        [paid_at, *withdrawal_ids, org_id],
    )
    await conn.commit()
    rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def link_to_invoice(withdrawal_id: str, invoice_id: str) -> bool:
    """Set invoice_id and mark as invoiced. Returns False if already linked.

    Called by finance context via facade.
    """
    conn = get_connection()
    cursor = await conn.execute(
        "UPDATE withdrawals SET invoice_id = $1, payment_status = 'invoiced' "
        "WHERE id = $2 AND invoice_id IS NULL",
        (invoice_id, withdrawal_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def unlink_from_invoice(withdrawal_ids: list[str]) -> None:
    """Clear invoice link and reset to unpaid. Called by finance context via facade."""
    if not withdrawal_ids:
        return
    conn = get_connection()
    placeholders = ",".join(f"${i}" for i in range(1, 1 + len(withdrawal_ids)))
    await conn.execute(
        f"UPDATE withdrawals SET invoice_id = NULL, payment_status = 'unpaid' WHERE id IN ({placeholders})",
        withdrawal_ids,
    )
    await conn.commit()


async def mark_paid_by_invoice(invoice_id: str, paid_at: str) -> None:
    """Mark all withdrawals linked to an invoice as paid. Called by finance context via facade."""
    conn = get_connection()
    await conn.execute(
        "UPDATE withdrawals SET payment_status = 'paid', paid_at = $1 WHERE invoice_id = $2",
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
    n = 2
    date_filter = ""
    if start_date:
        date_filter += f" AND w.created_at >= ${n}"
        params.append(start_date)
        n += 1
    if end_date:
        date_filter += f" AND w.created_at <= ${n}"
        params.append(end_date)
        n += 1
    query = (
        "SELECT wi.product_id, SUM(wi.quantity) AS total_qty"
        " FROM withdrawal_items wi"
        " JOIN withdrawals w ON wi.withdrawal_id = w.id"
        " WHERE w.organization_id = $1"
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
    n = 2
    date_filter = ""
    if start_date:
        date_filter += f" AND w.created_at >= ${n}"
        params.append(start_date)
        n += 1
    if end_date:
        date_filter += f" AND w.created_at <= ${n}"
        params.append(end_date)
        n += 1
    query = (
        "SELECT"
        " CASE"
        " WHEN w.payment_status = 'paid' THEN 'Paid'"
        " WHEN w.invoice_id IS NOT NULL THEN 'Invoiced'"
        " ELSE 'Unpaid'"
        " END AS status,"
        " ROUND(CAST(SUM(w.total) AS NUMERIC), 2) AS total"
        " FROM withdrawals w"
        " WHERE w.organization_id = $1"
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
