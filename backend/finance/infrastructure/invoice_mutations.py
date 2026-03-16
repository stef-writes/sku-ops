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
    n = 1
    set_clauses = []
    params = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = ${n}")
        params.append(v)
        n += 1
    params.append(invoice_id)
    q = f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ${n}"
    n += 1
    q += f" AND organization_id = ${n}"
    params.append(org_id)
    await conn.execute(q, params)
    await conn.commit()
    return await get_by_id(invoice_id)


async def replace_line_items(invoice_id: str, line_items: list[dict]) -> float:
    """Delete existing line items and insert new ones. Returns computed subtotal."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT id FROM invoices WHERE id = $1 AND organization_id = $2",
        (invoice_id, org_id),
    )
    if not await cursor.fetchone():
        raise ValueError(f"Invoice {invoice_id} not found in this organisation")
    await conn.execute("DELETE FROM invoice_line_items WHERE invoice_id = $1", (invoice_id,))
    subtotal = 0.0
    for item in line_items:
        amt = round(float(item.get("quantity", 1)) * float(item.get("unit_price", 0)), 2)
        item_id = item.get("id") or str(uuid4())
        cost_val = float(item.get("cost", 0))
        await conn.execute(
            """INSERT INTO invoice_line_items
               (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
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
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT id FROM invoices WHERE id = $1 AND organization_id = $2",
        (invoice_id, org_id),
    )
    if not await cursor.fetchone():
        raise ValueError(f"Invoice {invoice_id} not found in this organisation")
    subtotal = 0.0
    for item in line_items:
        qty = item.get("quantity", 1)
        price = item.get("unit_price") or item.get("price") or 0
        amt = round(qty * float(price), 2)
        cost_val = float(item.get("cost", 0))
        await conn.execute(
            """INSERT INTO invoice_line_items
               (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
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
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT id FROM invoices WHERE id = $1 AND organization_id = $2",
        (invoice_id, org_id),
    )
    if not await cursor.fetchone():
        raise ValueError(f"Invoice {invoice_id} not found in this organisation")
    await conn.execute(
        "INSERT INTO invoice_withdrawals (invoice_id, withdrawal_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        (invoice_id, withdrawal_id),
    )
    await conn.commit()


async def unlink_withdrawals(invoice_id: str) -> list[str]:
    """Remove all withdrawal links for an invoice. Returns the unlinked withdrawal IDs."""
    conn = get_connection()
    org_id = get_org_id()
    guard = await conn.execute(
        "SELECT id FROM invoices WHERE id = $1 AND organization_id = $2",
        (invoice_id, org_id),
    )
    if not await guard.fetchone():
        raise ValueError(f"Invoice {invoice_id} not found in this organisation")
    cursor = await conn.execute(
        "SELECT withdrawal_id FROM invoice_withdrawals WHERE invoice_id = $1",
        (invoice_id,),
    )
    rows = await cursor.fetchall()
    wids = [r[0] for r in rows]
    await conn.execute("DELETE FROM invoice_withdrawals WHERE invoice_id = $1", (invoice_id,))
    await conn.commit()
    return wids


async def soft_delete(invoice_id: str) -> None:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET status = 'deleted', deleted_at = $1, updated_at = $2 WHERE id = $3 AND organization_id = $4",
        (now, now, invoice_id, org_id),
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
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)""",
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
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT invoice_id FROM invoice_withdrawals WHERE withdrawal_id = $1",
        (withdrawal_id,),
    )
    row = await cursor.fetchone()
    if not row or not row[0]:
        return
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET status = 'paid', updated_at = $1 WHERE id = $2 AND organization_id = $3",
        (now, row[0], org_id),
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
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE invoices SET subtotal = $1, tax = $2, total = $3, updated_at = $4 WHERE id = $5 AND organization_id = $6",
        (subtotal, tax, total, now, invoice_id, org_id),
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
    org_id = get_org_id()
    await conn.execute(
        "UPDATE invoices SET billing_entity = $1, contact_name = $2, updated_at = $3 WHERE id = $4 AND organization_id = $5",
        (billing_entity, contact_name, updated_at, invoice_id, org_id),
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
    org_id = get_org_id()
    fields = {**fields, "updated_at": datetime.now(UTC).isoformat()}
    n = 1
    set_clauses = []
    params: list = []
    for k, v in fields.items():
        set_clauses.append(f"{k} = ${n}")
        params.append(v)
        n += 1
    params.append(invoice_id)
    n += 1
    params.append(org_id)
    await conn.execute(
        f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ${n - 1} AND organization_id = ${n}",
        params,
    )
    await conn.commit()
