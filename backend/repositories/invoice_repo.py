"""Invoice repository."""
import json
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone

from db import get_connection


def _invoice_row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return dict(row) if hasattr(row, "keys") else None


def _line_item_row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else None
    if d and "quantity" in d:
        d["quantity"] = float(d["quantity"])
    if d and "unit_price" in d:
        d["unit_price"] = float(d["unit_price"])
    if d and "amount" in d:
        d["amount"] = float(d["amount"])
    return d


async def _next_invoice_number(conn=None) -> str:
    """Generate next invoice number: INV-00001, INV-00002, etc."""
    in_transaction = conn is not None
    conn = conn or get_connection()
    await conn.execute(
        """INSERT INTO invoice_counters (key, counter) VALUES ('inv', 1)
           ON CONFLICT(key) DO UPDATE SET counter = counter + 1""",
    )
    cursor = await conn.execute(
        "SELECT counter FROM invoice_counters WHERE key = 'inv'",
    )
    row = await cursor.fetchone()
    if not in_transaction:
        await conn.commit()
    num = row[0] if row else 1
    return f"INV-{str(num).zfill(5)}"


async def insert(invoice_dict: dict) -> dict:
    conn = get_connection()
    invoice_id = invoice_dict.get("id") or str(uuid4())
    invoice_number = invoice_dict.get("invoice_number") or await _next_invoice_number()
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        """INSERT INTO invoices (id, invoice_number, billing_entity, contact_name, contact_email,
           status, subtotal, tax, total, notes, xero_invoice_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            invoice_id,
            invoice_number,
            invoice_dict.get("billing_entity", ""),
            invoice_dict.get("contact_name", ""),
            invoice_dict.get("contact_email", ""),
            invoice_dict.get("status", "draft"),
            float(invoice_dict.get("subtotal", 0)),
            float(invoice_dict.get("tax", 0)),
            float(invoice_dict.get("total", 0)),
            invoice_dict.get("notes"),
            invoice_dict.get("xero_invoice_id"),
            invoice_dict.get("created_at") or now,
            invoice_dict.get("updated_at") or now,
        ),
    )
    await conn.commit()
    return await get_by_id(invoice_id)


async def get_by_id(invoice_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM invoices WHERE id = ?",
        (invoice_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    inv = _invoice_row_to_dict(row)

    # Load line items
    cursor = await conn.execute(
        "SELECT * FROM invoice_line_items WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    )
    rows = await cursor.fetchall()
    inv["line_items"] = [_line_item_row_to_dict(r) for r in rows]

    # Load withdrawal IDs
    cursor = await conn.execute(
        "SELECT withdrawal_id FROM invoice_withdrawals WHERE invoice_id = ?",
        (invoice_id,),
    )
    rows = await cursor.fetchall()
    inv["withdrawal_ids"] = [r[0] for r in rows]

    return inv


async def list_invoices(
    status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000,
) -> list:
    conn = get_connection()
    query = "SELECT * FROM invoices WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if billing_entity:
        query += " AND billing_entity = ?"
        params.append(billing_entity)
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

    result = []
    for row in rows:
        inv = _invoice_row_to_dict(row)
        # Count withdrawals for list view
        cursor2 = await conn.execute(
            "SELECT COUNT(*) FROM invoice_withdrawals WHERE invoice_id = ?",
            (inv["id"],),
        )
        count_row = await cursor2.fetchone()
        inv["withdrawal_count"] = count_row[0] if count_row else 0
        result.append(inv)
    return result


async def update(
    invoice_id: str,
    billing_entity: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    tax: Optional[float] = None,
    line_items: Optional[list] = None,
) -> Optional[dict]:
    conn = get_connection()
    inv = await get_by_id(invoice_id)
    if not inv:
        return None

    now = datetime.now(timezone.utc).isoformat()

    if line_items is not None:
        # Replace line items
        await conn.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
        subtotal = 0.0
        for item in line_items:
            amt = round(float(item.get("quantity", 1)) * float(item.get("unit_price", 0)), 2)
            item_id = item.get("id") or str(uuid4())
            await conn.execute(
                """INSERT INTO invoice_line_items (id, invoice_id, description, quantity, unit_price, amount, product_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id,
                    invoice_id,
                    item.get("description", ""),
                    float(item.get("quantity", 1)),
                    float(item.get("unit_price", 0)),
                    amt,
                    item.get("product_id"),
                ),
            )
            subtotal += amt
        tax_val = tax if tax is not None else inv.get("tax", 0)
        total = round(subtotal + tax_val, 2)
        await conn.execute(
            """UPDATE invoices SET subtotal = ?, tax = ?, total = ?, updated_at = ? WHERE id = ?""",
            (subtotal, tax_val, total, now, invoice_id),
        )
    else:
        # Update fields only
        updates = []
        params = []
        if billing_entity is not None:
            updates.append("billing_entity = ?")
            params.append(billing_entity)
        if contact_name is not None:
            updates.append("contact_name = ?")
            params.append(contact_name)
        if contact_email is not None:
            updates.append("contact_email = ?")
            params.append(contact_email)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if tax is not None:
            inv_subtotal = inv.get("subtotal", 0)
            total = round(inv_subtotal + tax, 2)
            updates.append("tax = ?")
            params.append(tax)
            updates.append("total = ?")
            params.append(total)
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(invoice_id)
            await conn.execute(
                f"UPDATE invoices SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    await conn.commit()
    return await get_by_id(invoice_id)


async def add_withdrawals(invoice_id: str, withdrawal_ids: list) -> Optional[dict]:
    """Link withdrawals to invoice. Validates: unpaid, same billing_entity, not already on another invoice."""
    if not withdrawal_ids:
        return await get_by_id(invoice_id)
    conn = get_connection()

    from repositories.withdrawal_repo import withdrawal_repo

    withdrawals = []
    billing_entity = None
    contact_name = ""
    contact_email = ""
    for wid in withdrawal_ids:
        w = await withdrawal_repo.get_by_id(wid)
        if not w:
            raise ValueError(f"Withdrawal {wid} not found")
        if w.get("payment_status") != "unpaid":
            raise ValueError(f"Withdrawal {wid} is not unpaid")
        if w.get("invoice_id"):
            raise ValueError(f"Withdrawal {wid} is already on invoice {w['invoice_id']}")
        be = w.get("billing_entity") or ""
        if billing_entity is not None and be != billing_entity:
            raise ValueError("All withdrawals must share the same billing_entity")
        billing_entity = be
        if w.get("contractor_name"):
            contact_name = w["contractor_name"]
        if w.get("contractor_company") and not contact_name:
            contact_name = w["contractor_company"]
        withdrawals.append(w)

    inv = await get_by_id(invoice_id)
    if not inv:
        return None

    # Ensure invoice billing matches
    if inv.get("billing_entity") and inv["billing_entity"] != billing_entity:
        raise ValueError("Invoice billing_entity does not match withdrawals")
    if not inv.get("billing_entity") and billing_entity:
        await conn.execute(
            "UPDATE invoices SET billing_entity = ?, contact_name = ?, updated_at = ? WHERE id = ?",
            (billing_entity, contact_name or inv.get("contact_name", ""), datetime.now(timezone.utc).isoformat(), invoice_id),
        )

    # Copy line items from withdrawals
    total_subtotal = 0.0
    total_tax = 0.0
    for w in withdrawals:
        for item in w.get("items", []):
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
            amt = round(qty * price, 2)
            total_subtotal += amt
            await conn.execute(
                """INSERT INTO invoice_line_items (id, invoice_id, description, quantity, unit_price, amount, product_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    invoice_id,
                    item.get("name", ""),
                    qty,
                    price,
                    amt,
                    item.get("product_id"),
                ),
            )
        total_tax += w.get("tax", 0)

    total = round(total_subtotal + total_tax, 2)
    await conn.execute(
        "UPDATE invoices SET subtotal = ?, tax = ?, total = ?, updated_at = ? WHERE id = ?",
        (total_subtotal, total_tax, total, datetime.now(timezone.utc).isoformat(), invoice_id),
    )

    for wid in withdrawal_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO invoice_withdrawals (invoice_id, withdrawal_id) VALUES (?, ?)",
            (invoice_id, wid),
        )
        await conn.execute(
            "UPDATE withdrawals SET invoice_id = ? WHERE id = ?",
            (invoice_id, wid),
        )

    await conn.commit()
    return await get_by_id(invoice_id)


async def create_from_withdrawals(withdrawal_ids: list, conn=None) -> dict:
    """Create new invoice from unpaid withdrawals. All must share same billing_entity."""
    from repositories.withdrawal_repo import withdrawal_repo

    if not withdrawal_ids:
        raise ValueError("At least one withdrawal required")

    withdrawals = []
    billing_entity = None
    contact_name = ""
    contact_email = ""
    for wid in withdrawal_ids:
        w = await withdrawal_repo.get_by_id(wid)
        if not w:
            raise ValueError(f"Withdrawal {wid} not found")
        if w.get("payment_status") != "unpaid":
            raise ValueError(f"Withdrawal {wid} is not unpaid")
        if w.get("invoice_id"):
            raise ValueError(f"Withdrawal {wid} is already on invoice")
        be = w.get("billing_entity") or ""
        if billing_entity is not None and be != billing_entity:
            raise ValueError("All withdrawals must share the same billing_entity")
        billing_entity = be
        contact_name = w.get("contractor_name") or w.get("contractor_company") or ""
        withdrawals.append(w)

    inv_id = str(uuid4())
    total_subtotal = 0.0
    total_tax = 0.0
    in_transaction = conn is not None
    conn = conn or get_connection()
    now = datetime.now(timezone.utc).isoformat()
    invoice_number = await _next_invoice_number(conn)

    await conn.execute(
        """INSERT INTO invoices (id, invoice_number, billing_entity, contact_name, contact_email,
           status, subtotal, tax, total, notes, xero_invoice_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (inv_id, invoice_number, billing_entity or "", contact_name, contact_email or "", "draft", 0, 0, 0, None, None, now, now),
    )

    for w in withdrawals:
        for item in w.get("items", []):
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
            amt = round(qty * price, 2)
            total_subtotal += amt
            await conn.execute(
                """INSERT INTO invoice_line_items (id, invoice_id, description, quantity, unit_price, amount, product_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    inv_id,
                    item.get("name", ""),
                    qty,
                    price,
                    amt,
                    item.get("product_id"),
                ),
            )
        total_tax += w.get("tax", 0)

    total = round(total_subtotal + total_tax, 2)
    await conn.execute(
        "UPDATE invoices SET subtotal = ?, tax = ?, total = ? WHERE id = ?",
        (total_subtotal, total_tax, total, inv_id),
    )

    for wid in withdrawal_ids:
        await conn.execute(
            "INSERT INTO invoice_withdrawals (invoice_id, withdrawal_id) VALUES (?, ?)",
            (inv_id, wid),
        )
        await conn.execute(
            "UPDATE withdrawals SET invoice_id = ? WHERE id = ?",
            (inv_id, wid),
        )

    if not in_transaction:
        await conn.commit()
    return (await get_by_id(inv_id)) or {}


async def mark_paid_for_withdrawal(withdrawal_id: str) -> None:
    """When a withdrawal is marked paid, update its linked invoice to status 'paid'."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT invoice_id FROM withdrawals WHERE id = ? AND invoice_id IS NOT NULL",
        (withdrawal_id,),
    )
    row = await cursor.fetchone()
    if row and row[0]:
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE invoices SET status = 'paid', updated_at = ? WHERE id = ?",
            (now, row[0]),
        )
        await conn.commit()


async def delete_draft(invoice_id: str) -> bool:
    """Delete draft invoice and unlink withdrawals."""
    conn = get_connection()
    inv = await get_by_id(invoice_id)
    if not inv:
        return False
    if inv.get("status") != "draft":
        raise ValueError("Can only delete draft invoices")

    for wid in inv.get("withdrawal_ids", []):
        await conn.execute(
            "UPDATE withdrawals SET invoice_id = NULL WHERE id = ?",
            (wid,),
        )
    await conn.execute("DELETE FROM invoice_withdrawals WHERE invoice_id = ?", (invoice_id,))
    await conn.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
    await conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    await conn.commit()
    return True


class InvoiceRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_invoices = staticmethod(list_invoices)
    update = staticmethod(update)
    add_withdrawals = staticmethod(add_withdrawals)
    create_from_withdrawals = staticmethod(create_from_withdrawals)
    mark_paid_for_withdrawal = staticmethod(mark_paid_for_withdrawal)
    delete_draft = staticmethod(delete_draft)


invoice_repo = InvoiceRepo()
