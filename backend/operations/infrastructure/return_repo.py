"""Return repository."""

import json
from uuid import uuid4

from operations.domain.returns import MaterialReturn
from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if d and "items" in d and isinstance(d["items"], str):
        d["items"] = json.loads(d["items"]) if d["items"] else []
    return d


async def insert(ret: MaterialReturn | dict, conn=None) -> None:
    ret_dict = ret if isinstance(ret, dict) else ret.model_dump()
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = ret_dict.get("organization_id") or DEFAULT_ORG_ID
    items_json = json.dumps(
        [i if isinstance(i, dict) else i.model_dump() for i in ret_dict["items"]]
    )
    await conn.execute(
        """INSERT INTO returns (id, withdrawal_id, contractor_id, contractor_name,
           billing_entity, job_id, items, subtotal, tax, total, cost_total,
           reason, notes, credit_note_id, processed_by_id, processed_by_name,
           organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ret_dict["id"],
            ret_dict["withdrawal_id"],
            ret_dict["contractor_id"],
            ret_dict.get("contractor_name", ""),
            ret_dict.get("billing_entity", ""),
            ret_dict.get("job_id", ""),
            items_json,
            ret_dict["subtotal"],
            ret_dict["tax"],
            ret_dict["total"],
            ret_dict["cost_total"],
            ret_dict.get("reason", "other"),
            ret_dict.get("notes"),
            ret_dict.get("credit_note_id"),
            ret_dict.get("processed_by_id", ""),
            ret_dict.get("processed_by_name", ""),
            org_id,
            ret_dict.get("created_at", ""),
            ret_dict.get("updated_at", ""),
        ),
    )
    # Write normalized items
    for item in ret_dict["items"]:
        i = (
            item
            if isinstance(item, dict)
            else (item.model_dump() if hasattr(item, "model_dump") else item)
        )
        qty = float(i.get("quantity", 0))
        price = float(i.get("unit_price") or i.get("price") or 0)
        cost = float(i.get("cost", 0))
        await conn.execute(
            """INSERT INTO return_items
               (id, return_id, product_id, sku, name, quantity, unit_price, cost, unit, amount, cost_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                ret_dict["id"],
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

    if not in_transaction:
        await conn.commit()


async def get_by_id(return_id: str, organization_id: str | None = None) -> dict | None:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT * FROM returns WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
            (return_id, organization_id),
        )
    else:
        cursor = await conn.execute("SELECT * FROM returns WHERE id = ?", (return_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def list_returns(
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    organization_id: str | None = None,
) -> list:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
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
    return [_row_to_dict(r) for r in rows]


async def list_by_withdrawal(withdrawal_id: str, organization_id: str | None = None) -> list:
    conn = get_connection()
    params: list = [withdrawal_id]
    where = "WHERE withdrawal_id = ?"
    if organization_id:
        where += " AND (organization_id = ? OR organization_id IS NULL)"
        params.append(organization_id)
    cursor = await conn.execute(
        "SELECT * FROM returns " + where + " ORDER BY created_at DESC",
        params,
    )
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


class ReturnRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_returns = staticmethod(list_returns)
    list_by_withdrawal = staticmethod(list_by_withdrawal)


return_repo = ReturnRepo()
