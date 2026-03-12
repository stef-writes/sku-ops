"""Invoice repo — mutation operations (updates, line-item management, linking)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from finance.infrastructure._invoice_fetch import get_by_id
from shared.infrastructure.database import get_connection, get_org_id

if TYPE_CHECKING:
    from finance.domain.invoice import InvoiceWithDetails


async def update_fields(
    invoice_id: str,
    updates: dict,
) -> InvoiceWithDetails | None:
    """Update arbitrary invoice columns from a pre-validated dict."""
    if not updates:
        return await get_by_id(invoice_id)
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    updates["updated_at"] = now
    set_clauses = [f"{k} = ?" for k in updates]
    params = list(updates.values())
    params.append(invoice_id)
    q = f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ?"
    q += " AND organization_id = ?"
    params.append(org_id)
    await conn.execute(q, params)
    await conn.commit()
    return await get_by_id(invoice_id)


async def replace_line_items(invoice_id: str, line_items: list[dict]) -> float:
    """Delete existing line items and insert new ones. Returns computed subtotal."""
    conn = get_connection()
    await conn.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
    subtotal = 0.0
    for item in line_items:
        amt = round(float(item.get("quantity", 1)) * float(item.get("unit_price", 0)), 2)
        item_id = item.get("id") or str(uuid4())
        cost_val = float(item.get("cost", 0))
        await conn.execute(
            """INSERT INTO invoice_line_items
               (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                invoice_id,
                item.get("description", ""),
                float(item.get("quantity", 1)),
                float(item.get("unit_price", 0)),
                amt,
                cost_val,
                item.get("product_id"),
                item.get("job_id"),
                item.get("unit") or "each",
                float(item.get("sell_cost") or cost_val),
            ),
        )
        subtotal += amt
    await conn.commit()
    return subtotal


async def insert_line_items(invoice_id: str, line_items: list[dict]) -> float:
    """Append line items without deleting existing ones. Returns subtotal of inserted items."""
    conn = get_connection()
    subtotal = 0.0
    for item in line_items:
        qty = item.get("quantity", 1)
        price = item.get("unit_price") or item.get("price") or 0
        amt = round(qty * float(price), 2)
        cost_val = float(item.get("cost", 0))
        await conn.execute(
            """INSERT INTO invoice_line_items
               (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                invoice_id,
                item.get("description") or item.get("name", ""),
                qty,
                float(price),
                amt,
                cost_val,
                item.get("product_id"),
                item.get("job_id"),
                item.get("unit") or "each",
                float(item.get("sell_cost") or cost_val),
            ),
        )
        subtotal += amt
    await conn.commit()
    return subtotal


async def link_withdrawal(invoice_id: str, withdrawal_id: str) -> None:
    conn = get_connection()
    await conn.execute(
        "INSERT OR IGNORE INTO invoice_withdrawals (invoice_id, withdrawal_id) VALUES (?, ?)",
        (invoice_id, withdrawal_id),
    )
    await conn.commit()


async def unlink_withdrawals(invoice_id: str) -> list[str]:
    """Remove all withdrawal links for an invoice. Returns the unlinked withdrawal IDs."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT withdrawal_id FROM invoice_withdrawals WHERE invoice_id = ?",
        (invoice_id,),
    )
    rows = await cursor.fetchall()
    wids = [r[0] for r in rows]
    await conn.execute("DELETE FROM invoice_withdrawals WHERE invoice_id = ?", (invoice_id,))
    await conn.commit()
    return wids


async def soft_delete(invoice_id: str) -> None:
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET status = 'deleted', deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, invoice_id),
    )
    await conn.commit()


async def insert_invoice_row(
    inv_id: str,
    invoice_number: str,
    billing_entity: str,
    contact_name: str,
    contact_email: str,
    tax_rate: float,
    payment_terms: str,
    due_date: str,
    now: str,
) -> None:
    """Insert a bare invoice row (no line items)."""
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        """INSERT INTO invoices (id, invoice_number, billing_entity, contact_name, contact_email,
           status, subtotal, tax, tax_rate, total, amount_credited, notes,
           invoice_date, due_date, payment_terms, billing_address, po_reference, currency,
           approved_by_id, approved_at,
           xero_invoice_id, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            inv_id,
            invoice_number,
            billing_entity,
            contact_name,
            contact_email,
            "draft",
            0,
            0,
            tax_rate,
            0,
            0,
            None,
            now,
            due_date,
            payment_terms,
            "",
            "",
            "USD",
            None,
            None,
            None,
            org_id,
            now,
            now,
        ),
    )
    await conn.commit()


async def mark_paid_for_withdrawal(withdrawal_id: str) -> None:
    """When a withdrawal is marked paid, update its linked invoice to status 'paid'.

    Uses the finance-owned invoice_withdrawals bridge table to find the linked invoice.
    """
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT invoice_id FROM invoice_withdrawals WHERE withdrawal_id = ?",
        (withdrawal_id,),
    )
    row = await cursor.fetchone()
    if not row or not row[0]:
        return
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET status = 'paid', updated_at = ? WHERE id = ?",
        (now, row[0]),
    )
    await conn.commit()


async def update_invoice_totals(
    invoice_id: str,
    subtotal: float,
    tax: float,
    total: float,
) -> None:
    """Update the computed financial totals on an invoice row."""
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET subtotal = ?, tax = ?, total = ?, updated_at = ? WHERE id = ?",
        (subtotal, tax, total, now, invoice_id),
    )
    await conn.commit()


async def update_invoice_billing(
    invoice_id: str,
    billing_entity: str,
    contact_name: str,
    updated_at: str,
) -> None:
    """Update billing entity and contact name on an invoice row."""
    conn = get_connection()
    await conn.execute(
        "UPDATE invoices SET billing_entity = ?, contact_name = ?, updated_at = ? WHERE id = ?",
        (billing_entity, contact_name, updated_at, invoice_id),
    )
    await conn.commit()


async def update_invoice_fields_dynamic(
    invoice_id: str,
    fields: dict[str, Any],
) -> None:
    """Update arbitrary invoice columns from a pre-validated dict.

    Validation belongs in the application layer. This function only persists.
    """
    if not fields:
        return
    conn = get_connection()
    fields = {**fields, "updated_at": datetime.now(UTC).isoformat()}
    set_clauses = [f"{k} = ?" for k in fields]
    params: list = list(fields.values())
    params.append(invoice_id)
    await conn.execute(
        f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ?",
        params,
    )
    await conn.commit()
