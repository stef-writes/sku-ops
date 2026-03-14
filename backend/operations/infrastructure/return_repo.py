"""Return repository."""

import json
from uuid import uuid4

from operations.domain.returns import MaterialReturn
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> MaterialReturn | None:
    if row is None:
        return None
    d = dict(row)
    if "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return MaterialReturn.model_validate(d)


async def insert(ret: MaterialReturn) -> None:
    conn = get_connection()
    org_id = ret.organization_id or get_org_id()
    items_json = json.dumps([i.model_dump() for i in ret.items])
    await conn.execute(
        """INSERT INTO returns (id, withdrawal_id, contractor_id, contractor_name,
           billing_entity, job_id, items, subtotal, tax, total, cost_total,
           reason, notes, credit_note_id, processed_by_id, processed_by_name,
           organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ret.id,
            ret.withdrawal_id,
            ret.contractor_id,
            ret.contractor_name,
            ret.billing_entity,
            ret.job_id,
            items_json,
            ret.subtotal,
            ret.tax,
            ret.total,
            ret.cost_total,
            ret.reason,
            ret.notes,
            ret.credit_note_id,
            ret.processed_by_id,
            ret.processed_by_name,
            org_id,
            ret.created_at,
            ret.updated_at,
        ),
    )
    for item in ret.items:
        qty = float(item.quantity)
        price = float(item.unit_price)
        cost = float(item.cost)
        await conn.execute(
            """INSERT INTO return_items
               (id, return_id, product_id, sku, name, quantity, unit_price, cost, unit, amount, cost_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                ret.id,
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


async def get_by_id(return_id: str) -> MaterialReturn | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM returns WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
        (return_id, org_id),
    )
    row = await cursor.fetchone()
    return _row_to_model(row)


async def list_returns(
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[MaterialReturn]:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT * FROM returns WHERE (organization_id = ? OR organization_id IS NULL)"
    params: list = [org_id]
    if contractor_id:
        query += " AND contractor_id = ?"
        params.append(contractor_id)
    if withdrawal_id:
        query += " AND withdrawal_id = ?"
        params.append(withdrawal_id)
    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def list_by_withdrawal(withdrawal_id: str) -> list[MaterialReturn]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM returns WHERE withdrawal_id = ? AND (organization_id = ? OR organization_id IS NULL) ORDER BY created_at DESC",
        (withdrawal_id, org_id),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def link_credit_note(return_id: str, credit_note_id: str) -> None:
    """Set the credit_note_id on a return. Called by finance context via facade."""
    conn = get_connection()
    await conn.execute(
        "UPDATE returns SET credit_note_id = ? WHERE id = ?",
        (credit_note_id, return_id),
    )
    await conn.commit()


class ReturnRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_returns = staticmethod(list_returns)
    list_by_withdrawal = staticmethod(list_by_withdrawal)
    link_credit_note = staticmethod(link_credit_note)


return_repo = ReturnRepo()
