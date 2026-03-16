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
    await conn.execute(
        "UPDATE invoices SET xero_invoice_id = $1, xero_cogs_journal_id = $2,"
        " xero_sync_status = 'synced', updated_at = $3"
        " WHERE id = $4 AND organization_id = $5",
        (xero_invoice_id, xero_cogs_journal_id, datetime.now(UTC).isoformat(), invoice_id, org_id),
    )
    await conn.commit()


async def set_xero_sync_status(invoice_id: str, status: str) -> None:
    conn = get_connection()
    org_id = get_org_id()
    await conn.execute(
        "UPDATE invoices SET xero_sync_status = $1, updated_at = $2"
        " WHERE id = $3 AND organization_id = $4",
        (status, datetime.now(UTC).isoformat(), invoice_id, org_id),
    )
    await conn.commit()


def _row_to_invoice(row) -> Invoice | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Invoice.model_validate(d)


async def list_unsynced_invoices() -> list[Invoice]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, status, xero_sync_status, organization_id, created_at
           FROM invoices
           WHERE organization_id = $1
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
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_sync_status, organization_id,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = $1
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
        """SELECT id, invoice_number, billing_entity, total, status, organization_id, created_at
           FROM invoices
           WHERE organization_id = $1
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
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, organization_id, created_at
           FROM invoices
           WHERE organization_id = $1
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
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_cogs_journal_id, organization_id,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = $1
             AND xero_sync_status = 'cogs_stale'
             AND xero_invoice_id IS NOT NULL
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_invoice(r) for r in rows]
