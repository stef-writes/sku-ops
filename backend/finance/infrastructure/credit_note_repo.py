"""Credit note repository."""
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone

from shared.infrastructure.database import get_connection


async def _next_credit_note_number(organization_id: Optional[str] = None, conn=None) -> str:
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = organization_id or "default"
    key = f"{org_id}|cn"
    await conn.execute(
        """INSERT INTO invoice_counters (key, counter) VALUES (?, 1)
           ON CONFLICT(key) DO UPDATE SET counter = counter + 1""",
        (key,),
    )
    cursor = await conn.execute(
        "SELECT counter FROM invoice_counters WHERE key = ?", (key,)
    )
    row = await cursor.fetchone()
    if not in_transaction:
        await conn.commit()
    num = row[0] if row else 1
    return f"CN-{str(num).zfill(5)}"


def _row_to_dict(row) -> dict:
    d = dict(row) if hasattr(row, "keys") else {}
    for fld in ("quantity", "unit_price", "amount", "cost", "subtotal", "tax", "total", "cost_total"):
        if fld in d and d[fld] is not None:
            d[fld] = float(d[fld])
    return d


async def insert_credit_note(
    return_id: str,
    invoice_id: Optional[str],
    items: list,
    subtotal: float,
    tax: float,
    total: float,
    organization_id: Optional[str] = None,
    conn=None,
) -> dict:
    """Create a credit note linked to a return and its original invoice."""
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = organization_id or "default"
    cn_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    cn_number = await _next_credit_note_number(org_id, conn)

    billing_entity = ""
    if invoice_id:
        cursor = await conn.execute(
            "SELECT billing_entity FROM invoices WHERE id = ?", (invoice_id,)
        )
        inv_row = await cursor.fetchone()
        if inv_row:
            billing_entity = (dict(inv_row) if hasattr(inv_row, "keys") else {}).get("billing_entity", "")

    await conn.execute(
        """INSERT INTO credit_notes (id, credit_note_number, invoice_id, return_id,
           billing_entity, status, subtotal, tax, total, notes,
           xero_credit_note_id, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cn_id, cn_number, invoice_id, return_id,
            billing_entity, "draft", subtotal, tax, total, None,
            None, org_id, now, now,
        ),
    )

    for item in items:
        i = item if isinstance(item, dict) else item.model_dump()
        qty = i.get("quantity", 1)
        price = float(i.get("unit_price") or i.get("price") or 0)
        amt = round(qty * price, 2)
        await conn.execute(
            """INSERT INTO credit_note_line_items
               (id, credit_note_id, description, quantity, unit_price, amount, cost, product_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()), cn_id,
                i.get("name") or i.get("description", ""),
                qty, price, amt,
                float(i.get("cost", 0)),
                i.get("product_id"),
            ),
        )

    # Update the return record with the credit note ID
    await conn.execute(
        "UPDATE returns SET credit_note_id = ? WHERE id = ?", (cn_id, return_id)
    )

    if not in_transaction:
        await conn.commit()

    result = await get_by_id(cn_id)
    if not result:
        raise RuntimeError(f"Credit note {cn_id} missing immediately after insert")
    return result


async def get_by_id(credit_note_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT * FROM credit_notes WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
            (credit_note_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM credit_notes WHERE id = ?", (credit_note_id,)
        )
    row = await cursor.fetchone()
    if not row:
        return None
    cn = _row_to_dict(row)

    cursor = await conn.execute(
        "SELECT * FROM credit_note_line_items WHERE credit_note_id = ? ORDER BY id",
        (credit_note_id,),
    )
    rows = await cursor.fetchall()
    cn["line_items"] = [_row_to_dict(r) for r in rows]
    return cn


async def list_credit_notes(
    invoice_id: Optional[str] = None,
    billing_entity: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
    organization_id: Optional[str] = None,
) -> list:
    conn = get_connection()
    org_id = organization_id or "default"
    query = "SELECT * FROM credit_notes WHERE (organization_id = ? OR organization_id IS NULL)"
    params: list = [org_id]
    if invoice_id:
        query += " AND invoice_id = ?"
        params.append(invoice_id)
    if billing_entity:
        query += " AND billing_entity = ?"
        params.append(billing_entity)
    if status:
        query += " AND status = ?"
        params.append(status)
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


class CreditNoteRepo:
    insert_credit_note = staticmethod(insert_credit_note)
    get_by_id = staticmethod(get_by_id)
    list_credit_notes = staticmethod(list_credit_notes)


credit_note_repo = CreditNoteRepo()
