"""Invoice repo — Xero sync status updates and sync-related queries."""

from datetime import UTC, datetime

from finance.domain.invoice import Invoice
from shared.infrastructure.database import get_connection, get_org_id


async def set_xero_invoice_id(
    invoice_id: str,
    xero_invoice_id: str,
    xero_cogs_journal_id: str | None = None,
) -> None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [
        xero_invoice_id,
        xero_cogs_journal_id,
        datetime.now(UTC).isoformat(),
        invoice_id,
    ]
    where = "WHERE id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    upd_q = "UPDATE invoices SET xero_invoice_id = ?, xero_cogs_journal_id = ?, xero_sync_status = 'synced', updated_at = ? "
    upd_q += where
    await conn.execute(upd_q, params)
    await conn.commit()


async def set_xero_sync_status(invoice_id: str, status: str) -> None:
    conn = get_connection()
    org_id = get_org_id()
    params: list = [status, datetime.now(UTC).isoformat(), invoice_id]
    where = "WHERE id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    upd_q = "UPDATE invoices SET xero_sync_status = ?, updated_at = ? "
    upd_q += where
    await conn.execute(upd_q, params)
    await conn.commit()


def _row_to_invoice(row) -> Invoice | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Invoice.model_validate(d)


async def list_unsynced_invoices() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, status, xero_sync_status, created_at
           FROM invoices
           WHERE organization_id = ?
             AND status IN ('approved', 'sent')
             AND (xero_invoice_id IS NULL OR xero_sync_status = 'syncing')
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]


async def list_invoices_needing_reconciliation() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_sync_status,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = ?
             AND xero_invoice_id IS NOT NULL
             AND xero_sync_status != 'mismatch'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]


async def list_failed_invoices() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, status, created_at
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'failed'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]


async def list_mismatch_invoices() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, created_at
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'mismatch'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]


async def list_stale_cogs_invoices() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_cogs_journal_id,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'cogs_stale'
             AND xero_invoice_id IS NOT NULL
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]
