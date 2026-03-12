"""Invoice repository — core CRUD and the InvoiceRepo class facade.

Sub-modules:
  invoice_mutations   — field updates, line-item ops, withdrawal linking, soft delete
  invoice_xero_queries — Xero sync status updates and sync-related listing queries
"""

from datetime import UTC, datetime
from uuid import uuid4

from finance.domain.invoice import (
    Invoice,
    InvoiceWithDetails,
    compute_due_date,
)

# Re-export mutation functions so existing imports keep working
from finance.infrastructure.invoice_mutations import (
    insert_invoice_row,
    insert_line_items,
    link_withdrawal,
    mark_paid_for_withdrawal,
    replace_line_items,
    soft_delete,
    unlink_withdrawals,
    update_fields,
)

# Re-export Xero sync functions
from finance.infrastructure.invoice_xero_queries import (
    list_failed_invoices,
    list_invoices_needing_reconciliation,
    list_mismatch_invoices,
    list_stale_cogs_invoices,
    list_unsynced_invoices,
    set_xero_invoice_id,
    set_xero_sync_status,
)
from finance.infrastructure._invoice_fetch import (
    _build_invoice_with_details,
    _row_to_model,
    get_by_id,
)
from shared.infrastructure.database import get_connection, get_org_id


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


async def next_invoice_number() -> str:
    """Generate next invoice number: INV-00001, INV-00002, etc. Org-scoped counter."""
    conn = get_connection()
    org_id = get_org_id()
    key = f"{org_id}|inv"
    await conn.execute(
        """INSERT INTO invoice_counters (key, counter) VALUES (?, 1)
           ON CONFLICT(key) DO UPDATE SET counter = counter + 1""",
        (key,),
    )
    cursor = await conn.execute(
        "SELECT counter FROM invoice_counters WHERE key = ?",
        (key,),
    )
    row = await cursor.fetchone()
    await conn.commit()
    num = row[0] if row else 1
    return f"INV-{str(num).zfill(5)}"


async def insert(invoice: Invoice | dict) -> InvoiceWithDetails | None:
    invoice_dict = invoice if isinstance(invoice, dict) else invoice.model_dump()
    conn = get_connection()
    org_id = get_org_id()
    invoice_id = invoice_dict.get("id") or str(uuid4())
    invoice_number = invoice_dict.get("invoice_number") or await next_invoice_number()
    now = datetime.now(UTC).isoformat()
    inv_date = invoice_dict.get("invoice_date") or now
    payment_terms = invoice_dict.get("payment_terms") or "net_30"
    due_date = invoice_dict.get("due_date") or compute_due_date(inv_date, payment_terms)
    await conn.execute(
        """INSERT INTO invoices (id, invoice_number, billing_entity, contact_name, contact_email,
           status, subtotal, tax, tax_rate, total, amount_credited, notes,
           invoice_date, due_date, payment_terms, billing_address, po_reference, currency,
           approved_by_id, approved_at,
           xero_invoice_id, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            invoice_id,
            invoice_number,
            invoice_dict.get("billing_entity", ""),
            invoice_dict.get("contact_name", ""),
            invoice_dict.get("contact_email", ""),
            invoice_dict.get("status", "draft"),
            float(invoice_dict.get("subtotal", 0)),
            float(invoice_dict.get("tax", 0)),
            float(invoice_dict.get("tax_rate", 0)),
            float(invoice_dict.get("total", 0)),
            float(invoice_dict.get("amount_credited", 0)),
            invoice_dict.get("notes"),
            inv_date,
            due_date,
            payment_terms,
            invoice_dict.get("billing_address", ""),
            invoice_dict.get("po_reference", ""),
            invoice_dict.get("currency", "USD"),
            invoice_dict.get("approved_by_id"),
            invoice_dict.get("approved_at"),
            invoice_dict.get("xero_invoice_id"),
            org_id,
            invoice_dict.get("created_at") or now,
            invoice_dict.get("updated_at") or now,
        ),
    )
    await conn.commit()
    return await get_by_id(invoice_id)


async def list_invoices(
    status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 1000,
) -> list:
    conn = get_connection()
    org_id = get_org_id()
    query = "SELECT * FROM invoices WHERE (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL"
    params: list = [org_id]
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

    invoice_ids: list[str] = []
    result: list[Invoice] = []
    for row in rows:
        inv = _row_to_model(row)
        if inv is None:
            continue
        invoice_ids.append(inv.id)
        result.append(inv)

    if invoice_ids:
        placeholders = ",".join("?" for _ in invoice_ids)
        count_q = "SELECT invoice_id, COUNT(*) FROM invoice_withdrawals WHERE invoice_id IN ("
        count_q += placeholders
        count_q += ") GROUP BY invoice_id"
        count_cursor = await conn.execute(count_q, invoice_ids)
        counts = {r[0]: r[1] for r in await count_cursor.fetchall()}
        for inv in result:
            inv.withdrawal_count = counts.get(inv.id, 0)

    return result


# ---------------------------------------------------------------------------
# Class facade — preserves static-method interface for all consumers
# ---------------------------------------------------------------------------


class InvoiceRepo:
    # Core CRUD
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_invoices = staticmethod(list_invoices)
    next_invoice_number = staticmethod(next_invoice_number)

    # Mutations (from invoice_mutations)
    update_fields = staticmethod(update_fields)
    replace_line_items = staticmethod(replace_line_items)
    insert_line_items = staticmethod(insert_line_items)
    link_withdrawal = staticmethod(link_withdrawal)
    unlink_withdrawals = staticmethod(unlink_withdrawals)
    soft_delete = staticmethod(soft_delete)
    insert_invoice_row = staticmethod(insert_invoice_row)
    mark_paid_for_withdrawal = staticmethod(mark_paid_for_withdrawal)

    # Xero sync (from invoice_xero_queries)
    set_xero_invoice_id = staticmethod(set_xero_invoice_id)
    set_xero_sync_status = staticmethod(set_xero_sync_status)
    list_unsynced_invoices = staticmethod(list_unsynced_invoices)
    list_invoices_needing_reconciliation = staticmethod(list_invoices_needing_reconciliation)
    list_failed_invoices = staticmethod(list_failed_invoices)
    list_mismatch_invoices = staticmethod(list_mismatch_invoices)
    list_stale_cogs_invoices = staticmethod(list_stale_cogs_invoices)


invoice_repo = InvoiceRepo()
