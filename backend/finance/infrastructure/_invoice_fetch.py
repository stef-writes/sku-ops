"""Low-level invoice fetch helpers — imported by both invoice_repo and invoice_mutations.

Extracted into its own module so that invoice_mutations can call get_by_id without
creating a circular import with invoice_repo.
"""

from finance.domain.invoice import Invoice, InvoiceLineItem, InvoiceWithDetails
from shared.infrastructure.database import get_connection, get_org_id


def _row_to_model(row) -> Invoice | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return Invoice.model_validate(d)


def _build_invoice_with_details(
    inv_row,
    line_item_rows,
    withdrawal_ids: list[str],
) -> InvoiceWithDetails:
    d = dict(inv_row)
    items = []
    for r in line_item_rows:
        li = dict(r)
        for col in ("quantity", "unit_price", "amount", "cost", "sell_cost"):
            if col in li and li[col] is not None:
                li[col] = float(li[col])
        items.append(InvoiceLineItem.model_validate(li))
    d["line_items"] = items
    d["withdrawal_ids"] = withdrawal_ids
    return InvoiceWithDetails.model_validate(d)


async def get_by_id(invoice_id: str) -> InvoiceWithDetails | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM invoices WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
        (invoice_id, org_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    cursor = await conn.execute(
        "SELECT * FROM invoice_line_items WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    )
    li_rows = await cursor.fetchall()

    cursor = await conn.execute(
        "SELECT withdrawal_id FROM invoice_withdrawals WHERE invoice_id = ?",
        (invoice_id,),
    )
    w_rows = await cursor.fetchall()
    withdrawal_ids = [r[0] for r in w_rows]

    return _build_invoice_with_details(row, li_rows, withdrawal_ids)
