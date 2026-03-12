"""Credit note repository — pure persistence for credit notes and line items."""

from datetime import UTC, datetime
from uuid import uuid4

from finance.domain.credit_note import CreditNote, CreditNoteLineItem
from shared.infrastructure.database import get_connection, get_org_id, transaction


async def _next_credit_note_number() -> str:
    conn = get_connection()
    org_id = get_org_id()
    key = f"{org_id}|cn"
    await conn.execute(
        """INSERT INTO invoice_counters (key, counter) VALUES (?, 1)
           ON CONFLICT(key) DO UPDATE SET counter = counter + 1""",
        (key,),
    )
    cursor = await conn.execute("SELECT counter FROM invoice_counters WHERE key = ?", (key,))
    row = await cursor.fetchone()
    await conn.commit()
    num = row[0] if row else 1
    return f"CN-{str(num).zfill(5)}"


def _row_to_model(row) -> CreditNote | None:
    if row is None:
        return None
    d = dict(row) if hasattr(row, "keys") else {}
    if not d:
        return None
    for fld in (
        "quantity",
        "unit_price",
        "amount",
        "cost",
        "subtotal",
        "tax",
        "total",
        "cost_total",
    ):
        if fld in d and d[fld] is not None:
            d[fld] = float(d[fld])
    if d.get("organization_id") is None:
        d.pop("organization_id", None)
    return CreditNote.model_validate(d)


def _row_to_line_item(row) -> CreditNoteLineItem:
    d = dict(row) if hasattr(row, "keys") else {}
    for fld in ("quantity", "unit_price", "amount", "cost"):
        if fld in d and d[fld] is not None:
            d[fld] = float(d[fld])
    return CreditNoteLineItem.model_validate(d)


async def insert_credit_note(
    return_id: str,
    invoice_id: str | None,
    items: list,
    subtotal: float,
    tax: float,
    total: float,
) -> CreditNote:
    """Create a credit note linked to a return and its original invoice.

    Pure persistence — does NOT update the return record (that's cross-context
    orchestration owned by credit_note_service).
    """
    conn = get_connection()
    org_id = get_org_id()
    cn_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    cn_number = await _next_credit_note_number()

    billing_entity = ""
    if invoice_id:
        inv_params: list = [invoice_id]
        inv_where = "WHERE id = ?"
        inv_where += " AND (organization_id = ? OR organization_id IS NULL)"
        inv_params.append(org_id)
        cursor = await conn.execute("SELECT billing_entity FROM invoices " + inv_where, inv_params)
        inv_row = await cursor.fetchone()
        if inv_row:
            billing_entity = (dict(inv_row) if hasattr(inv_row, "keys") else {}).get(
                "billing_entity", ""
            )

    await conn.execute(
        """INSERT INTO credit_notes (id, credit_note_number, invoice_id, return_id,
           billing_entity, status, subtotal, tax, total, notes,
           xero_credit_note_id, organization_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cn_id,
            cn_number,
            invoice_id,
            return_id,
            billing_entity,
            "draft",
            subtotal,
            tax,
            total,
            None,
            None,
            org_id,
            now,
            now,
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
                str(uuid4()),
                cn_id,
                i.get("name") or i.get("description", ""),
                qty,
                price,
                amt,
                float(i.get("cost", 0)),
                i.get("product_id"),
            ),
        )

    await conn.commit()

    result = await get_by_id(cn_id)
    if not result:
        raise RuntimeError(f"Credit note {cn_id} missing immediately after insert")
    return result


async def get_by_id(credit_note_id: str) -> CreditNote | None:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        "SELECT * FROM credit_notes WHERE id = ? AND (organization_id = ? OR organization_id IS NULL)",
        (credit_note_id, org_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cn = _row_to_model(row)
    if cn is None:
        return None

    cursor = await conn.execute(
        "SELECT * FROM credit_note_line_items WHERE credit_note_id = ? ORDER BY id",
        (credit_note_id,),
    )
    rows = await cursor.fetchall()
    cn.line_items = [_row_to_line_item(r) for r in rows]
    return cn


async def list_credit_notes(
    invoice_id: str | None = None,
    billing_entity: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[CreditNote]:
    conn = get_connection()
    org_id = get_org_id()
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
    return [_row_to_model(r) for r in rows]


class ApplyCreditNoteResult:
    """Result of applying a credit note: the updated note plus metadata."""

    __slots__ = ("auto_paid", "credit_note", "invoice_id")

    def __init__(self, credit_note: CreditNote, auto_paid: bool, invoice_id: str):
        self.credit_note = credit_note
        self.auto_paid = auto_paid
        self.invoice_id = invoice_id


async def apply_credit_note(credit_note_id: str) -> ApplyCreditNoteResult:
    """Apply a draft credit note against its linked invoice.

    Increases invoices.amount_credited, sets credit note status to 'applied'.
    If the invoice balance_due reaches 0, marks the invoice as paid.

    NOTE: This is finance-only persistence. Cross-context orchestration
    (marking withdrawals paid) is handled by credit_note_service.apply_credit_note().
    """
    cn = await get_by_id(credit_note_id)
    if not cn:
        raise ValueError("Credit note not found")
    if cn.status != "draft":
        raise ValueError(f"Credit note is already {cn.status}")
    if not cn.invoice_id:
        raise ValueError("Credit note has no linked invoice")

    inv_id = cn.invoice_id
    cn_total = float(cn.total)

    auto_paid = False
    async with transaction() as conn:
        cursor = await conn.execute(
            "SELECT total, amount_credited, status FROM invoices WHERE id = ?", (inv_id,)
        )
        inv_row = await cursor.fetchone()
        if not inv_row:
            raise ValueError(f"Linked invoice {inv_id} not found")
        inv = dict(inv_row)
        new_credited = round(float(inv.get("amount_credited", 0)) + cn_total, 2)
        balance_due = round(float(inv["total"]) - new_credited, 2)
        now = datetime.now(UTC).isoformat()

        await conn.execute(
            "UPDATE invoices SET amount_credited = ?, updated_at = ? WHERE id = ?",
            (new_credited, now, inv_id),
        )

        if balance_due <= 0 and inv.get("status") != "paid":
            await conn.execute(
                "UPDATE invoices SET status = 'paid', updated_at = ? WHERE id = ?",
                (now, inv_id),
            )
            auto_paid = True

        await conn.execute(
            "UPDATE credit_notes SET status = 'applied', updated_at = ? WHERE id = ?",
            (now, credit_note_id),
        )

    updated = await get_by_id(credit_note_id)
    if not updated:
        raise RuntimeError(f"Credit note {credit_note_id} missing after apply")
    return ApplyCreditNoteResult(credit_note=updated, auto_paid=auto_paid, invoice_id=inv_id)


async def set_xero_credit_note_id(
    credit_note_id: str, xero_credit_note_id: str
) -> None:
    """Store the Xero credit note ID and mark as synced after a successful sync."""
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [xero_credit_note_id, now, credit_note_id]
    where = "WHERE id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    await conn.execute(
        "UPDATE credit_notes SET xero_credit_note_id = ?, xero_sync_status = 'synced', updated_at = ? "
        + where,
        params,
    )
    await conn.commit()


async def set_credit_note_sync_status(credit_note_id: str, status: str) -> None:
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    params: list = [status, now, credit_note_id]
    where = "WHERE id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    await conn.execute(
        "UPDATE credit_notes SET xero_sync_status = ?, updated_at = ? " + where,
        params,
    )
    await conn.commit()


async def list_unsynced_credit_notes() -> list[CreditNote]:
    """Return applied credit notes not yet synced to Xero."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, credit_note_number, billing_entity, total, status, created_at
           FROM credit_notes
           WHERE (organization_id = ? OR organization_id IS NULL)
             AND status = 'applied'
             AND xero_credit_note_id IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def list_credit_notes_needing_reconciliation() -> list[CreditNote]:
    """Return credit notes that have a Xero ID and are not already flagged as mismatch."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT cn.id, cn.credit_note_number, cn.billing_entity, cn.total,
                  cn.xero_credit_note_id, cn.xero_sync_status,
                  (SELECT COUNT(*) FROM credit_note_line_items WHERE credit_note_id = cn.id) AS line_count
           FROM credit_notes cn
           WHERE (cn.organization_id = ? OR cn.organization_id IS NULL)
             AND cn.xero_credit_note_id IS NOT NULL
             AND cn.xero_sync_status != 'mismatch'
           ORDER BY cn.created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def list_failed_credit_notes() -> list[CreditNote]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, credit_note_number, billing_entity, total, status, created_at
           FROM credit_notes
           WHERE (organization_id = ? OR organization_id IS NULL)
             AND xero_sync_status = 'failed'
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


async def list_mismatch_credit_notes() -> list[CreditNote]:
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT id, credit_note_number, billing_entity, total, xero_credit_note_id, created_at
           FROM credit_notes
           WHERE (organization_id = ? OR organization_id IS NULL)
             AND xero_sync_status = 'mismatch'
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_model(r) for r in rows]


class CreditNoteRepo:
    insert_credit_note = staticmethod(insert_credit_note)
    get_by_id = staticmethod(get_by_id)
    list_credit_notes = staticmethod(list_credit_notes)
    apply_credit_note = staticmethod(apply_credit_note)
    set_xero_credit_note_id = staticmethod(set_xero_credit_note_id)
    set_credit_note_sync_status = staticmethod(set_credit_note_sync_status)
    list_unsynced_credit_notes = staticmethod(list_unsynced_credit_notes)
    list_credit_notes_needing_reconciliation = staticmethod(
        list_credit_notes_needing_reconciliation
    )
    list_failed_credit_notes = staticmethod(list_failed_credit_notes)
    list_mismatch_credit_notes = staticmethod(list_mismatch_credit_notes)


credit_note_repo = CreditNoteRepo()
