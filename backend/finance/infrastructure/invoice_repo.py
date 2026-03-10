"""Invoice repository."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from finance.domain.invoice import Invoice, compute_due_date
from shared.infrastructure.config import DEFAULT_ORG_ID
from shared.infrastructure.database import get_connection, transaction

# Injected at module level by the API layer to avoid circular import with operations
_wiring: dict[str, Callable[..., Awaitable[dict | None]]] = {}


def set_withdrawal_getter(fn: Callable[..., Awaitable[dict | None]]) -> None:
    """Wire the withdrawal query function (called once at startup)."""
    _wiring["withdrawal_getter"] = fn


async def _get_withdrawal(wid: str, org_id: str) -> dict | None:
    """Fetch a withdrawal via the injected operations query."""
    getter = _wiring.get("withdrawal_getter")
    if getter is None:
        raise RuntimeError("withdrawal_getter not wired — call set_withdrawal_getter at startup")
    return await getter(wid, organization_id=org_id)


def _invoice_row_to_dict(row) -> dict:
    return dict(row)


def _line_item_row_to_dict(row) -> dict:
    d = dict(row)
    for col in ("quantity", "unit_price", "amount", "cost", "sell_cost"):
        if col in d and d[col] is not None:
            d[col] = float(d[col])
    return d


async def _next_invoice_number(organization_id: str | None = None, conn=None) -> str:
    """Generate next invoice number: INV-00001, INV-00002, etc. Org-scoped counter."""
    in_transaction = conn is not None
    conn = conn or get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
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
    if not in_transaction:
        await conn.commit()
    num = row[0] if row else 1
    return f"INV-{str(num).zfill(5)}"


async def insert(invoice: Invoice | dict) -> dict | None:
    invoice_dict = invoice if isinstance(invoice, dict) else invoice.model_dump()
    conn = get_connection()
    org_id = invoice_dict.get("organization_id") or DEFAULT_ORG_ID
    invoice_id = invoice_dict.get("id") or str(uuid4())
    invoice_number = invoice_dict.get("invoice_number") or await _next_invoice_number(org_id)
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


async def get_by_id(invoice_id: str, organization_id: str | None = None) -> dict | None:
    conn = get_connection()
    if organization_id:
        cursor = await conn.execute(
            "SELECT * FROM invoices WHERE id = ? AND (organization_id = ? OR organization_id IS NULL) AND deleted_at IS NULL",
            (invoice_id, organization_id),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM invoices WHERE id = ? AND deleted_at IS NULL",
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
    status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 1000,
    organization_id: str | None = None,
) -> list:
    conn = get_connection()
    org_id = organization_id or DEFAULT_ORG_ID
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

    invoice_ids = []
    result = []
    for row in rows:
        inv = _invoice_row_to_dict(row)
        invoice_ids.append(inv["id"])
        result.append(inv)

    if invoice_ids:
        placeholders = ",".join("?" for _ in invoice_ids)
        count_q = "SELECT invoice_id, COUNT(*) FROM invoice_withdrawals WHERE invoice_id IN ("
        count_q += placeholders
        count_q += ") GROUP BY invoice_id"
        count_cursor = await conn.execute(count_q, invoice_ids)
        counts = {r[0]: r[1] for r in await count_cursor.fetchall()}
        for inv in result:
            inv["withdrawal_count"] = counts.get(inv["id"], 0)
    else:
        for inv in result:
            inv["withdrawal_count"] = 0

    return result


async def update(
    invoice_id: str,
    billing_entity: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    status: str | None = None,
    notes: str | None = None,
    tax: float | None = None,
    tax_rate: float | None = None,
    invoice_date: str | None = None,
    due_date: str | None = None,
    payment_terms: str | None = None,
    billing_address: str | None = None,
    po_reference: str | None = None,
    line_items: list | None = None,
    organization_id: str | None = None,
) -> dict | None:
    inv = await get_by_id(invoice_id, organization_id=organization_id)
    if not inv:
        return None

    now = datetime.now(UTC).isoformat()

    async with transaction() as conn:
        if line_items is not None:
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
            tax_val = tax if tax is not None else float(inv.get("tax", 0))
            total = round(subtotal + tax_val, 2)
            sync_status_update = ""
            if inv.get("xero_invoice_id"):
                sync_status_update = ", xero_sync_status = 'cogs_stale'"
            upd_q = "UPDATE invoices SET subtotal = ?, tax = ?, total = ?, updated_at = ?"
            upd_q += sync_status_update
            upd_q += " WHERE id = ?"
            await conn.execute(upd_q, (subtotal, tax_val, total, now, invoice_id))
        else:
            updates: list[str] = []
            params: list = []
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
                inv_subtotal = float(inv.get("subtotal", 0))
                total = round(inv_subtotal + tax, 2)
                updates.append("tax = ?")
                params.append(tax)
                updates.append("total = ?")
                params.append(total)
            if tax_rate is not None:
                updates.append("tax_rate = ?")
                params.append(tax_rate)
            if invoice_date is not None:
                updates.append("invoice_date = ?")
                params.append(invoice_date)
            if due_date is not None:
                updates.append("due_date = ?")
                params.append(due_date)
            elif payment_terms is not None:
                inv_date = invoice_date or inv.get("invoice_date") or inv.get("created_at")
                updates.append("due_date = ?")
                params.append(compute_due_date(inv_date, payment_terms))
            if payment_terms is not None:
                updates.append("payment_terms = ?")
                params.append(payment_terms)
            if billing_address is not None:
                updates.append("billing_address = ?")
                params.append(billing_address)
            if po_reference is not None:
                updates.append("po_reference = ?")
                params.append(po_reference)
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(invoice_id)
                upd_q = "UPDATE invoices SET "
                upd_q += ", ".join(updates)
                upd_q += " WHERE id = ?"
                await conn.execute(upd_q, params)

        if status == "paid":
            await conn.execute(
                "UPDATE withdrawals SET payment_status = 'paid', paid_at = ? WHERE invoice_id = ?",
                (now, invoice_id),
            )

    return await get_by_id(invoice_id)


async def add_withdrawals(
    invoice_id: str, withdrawal_ids: list, organization_id: str | None = None
) -> dict | None:
    """Link withdrawals to invoice. Validates: unpaid, same billing_entity, not already on another invoice."""
    if not withdrawal_ids:
        return await get_by_id(invoice_id)
    org_id = organization_id or DEFAULT_ORG_ID

    withdrawals = []
    billing_entity = None
    contact_name = ""
    for wid in withdrawal_ids:
        w = await _get_withdrawal(wid, org_id)
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

    if inv.get("billing_entity") and inv["billing_entity"] != billing_entity:
        raise ValueError("Invoice billing_entity does not match withdrawals")

    async with transaction() as conn:
        if not inv.get("billing_entity") and billing_entity:
            await conn.execute(
                "UPDATE invoices SET billing_entity = ?, contact_name = ?, updated_at = ? WHERE id = ?",
                (
                    billing_entity,
                    contact_name or inv.get("contact_name", ""),
                    datetime.now(UTC).isoformat(),
                    invoice_id,
                ),
            )

        total_subtotal = 0.0
        total_tax = 0.0
        for w in withdrawals:
            for item in w.get("items", []):
                qty = item.get("quantity", 1)
                price = item.get("unit_price") or item.get("price") or 0
                amt = round(qty * float(price), 2)
                total_subtotal += amt
                cost_val = float(item.get("cost", 0))
                await conn.execute(
                    """INSERT INTO invoice_line_items
                       (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid4()),
                        invoice_id,
                        item.get("name", ""),
                        qty,
                        float(price),
                        amt,
                        cost_val,
                        item.get("product_id"),
                        w.get("job_id"),
                        item.get("unit") or "each",
                        float(item.get("sell_cost") or cost_val),
                    ),
                )
            total_tax += w.get("tax", 0)

        total = round(total_subtotal + total_tax, 2)
        await conn.execute(
            "UPDATE invoices SET subtotal = ?, tax = ?, total = ?, updated_at = ? WHERE id = ?",
            (total_subtotal, total_tax, total, datetime.now(UTC).isoformat(), invoice_id),
        )

        for wid in withdrawal_ids:
            await conn.execute(
                "INSERT OR IGNORE INTO invoice_withdrawals (invoice_id, withdrawal_id) VALUES (?, ?)",
                (invoice_id, wid),
            )
            await conn.execute(
                "UPDATE withdrawals SET invoice_id = ?, payment_status = 'invoiced' WHERE id = ?",
                (invoice_id, wid),
            )

    return await get_by_id(invoice_id)


async def create_from_withdrawals(
    withdrawal_ids: list, organization_id: str | None = None, conn=None
) -> dict:
    """Create new invoice from unpaid withdrawals. All must share same billing_entity."""
    if not withdrawal_ids:
        raise ValueError("At least one withdrawal required")

    org_id = organization_id or DEFAULT_ORG_ID
    withdrawals = []
    billing_entity = None
    contact_name = ""
    contact_email = ""
    for wid in withdrawal_ids:
        w = await _get_withdrawal(wid, org_id)
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
    now = datetime.now(UTC).isoformat()
    invoice_number = await _next_invoice_number(org_id, conn)
    payment_terms = "net_30"
    due_date = compute_due_date(now, payment_terms)
    first_tax_rate = withdrawals[0].get("tax_rate", 0) if withdrawals else 0

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
            billing_entity or "",
            contact_name,
            contact_email or "",
            "draft",
            0,
            0,
            first_tax_rate,
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

    for w in withdrawals:
        for item in w.get("items", []):
            qty = item.get("quantity", 1)
            price = item.get("unit_price") or item.get("price") or 0
            amt = round(qty * float(price), 2)
            total_subtotal += amt
            cost_val = float(item.get("cost", 0))
            await conn.execute(
                """INSERT INTO invoice_line_items
                   (id, invoice_id, description, quantity, unit_price, amount, cost, product_id, job_id, unit, sell_cost)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    inv_id,
                    item.get("name", ""),
                    qty,
                    float(price),
                    amt,
                    cost_val,
                    item.get("product_id"),
                    w.get("job_id"),
                    item.get("unit") or "each",
                    float(item.get("sell_cost") or cost_val),
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
            "UPDATE withdrawals SET invoice_id = ?, payment_status = 'invoiced' WHERE id = ?",
            (inv_id, wid),
        )

    if not in_transaction:
        await conn.commit()
    return (await get_by_id(inv_id)) or {}


async def mark_paid_for_withdrawal(withdrawal_id: str, organization_id: str | None = None) -> None:
    """When a withdrawal is marked paid, update its linked invoice to status 'paid'."""
    conn = get_connection()
    params: list = [withdrawal_id]
    where = "WHERE id = ? AND invoice_id IS NOT NULL"
    if organization_id:
        where += " AND (organization_id = ? OR organization_id IS NULL)"
        params.append(organization_id)
    sel_q = "SELECT invoice_id FROM withdrawals "
    sel_q += where
    cursor = await conn.execute(sel_q, params)
    row = await cursor.fetchone()
    if row and row[0]:
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            "UPDATE invoices SET status = 'paid', updated_at = ? WHERE id = ?",
            (now, row[0]),
        )
        await conn.commit()


async def set_xero_invoice_id(
    invoice_id: str,
    xero_invoice_id: str,
    xero_cogs_journal_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Store the Xero invoice ID (and optional COGS journal ID) and mark as synced."""
    conn = get_connection()
    params: list = [
        xero_invoice_id,
        xero_cogs_journal_id,
        datetime.now(UTC).isoformat(),
        invoice_id,
    ]
    where = "WHERE id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    upd_q = "UPDATE invoices SET xero_invoice_id = ?, xero_cogs_journal_id = ?, xero_sync_status = 'synced', updated_at = ? "
    upd_q += where
    await conn.execute(upd_q, params)
    await conn.commit()


async def set_xero_sync_status(
    invoice_id: str, status: str, organization_id: str | None = None
) -> None:
    """Update the Xero sync status for an invoice."""
    conn = get_connection()
    params: list = [status, datetime.now(UTC).isoformat(), invoice_id]
    where = "WHERE id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    upd_q = "UPDATE invoices SET xero_sync_status = ?, updated_at = ? "
    upd_q += where
    await conn.execute(upd_q, params)
    await conn.commit()


async def list_unsynced_invoices(organization_id: str) -> list:
    """Return invoices that are approved/sent but not yet synced to Xero,
    including those stuck in 'syncing' status from interrupted attempts."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, status, xero_sync_status, created_at
           FROM invoices
           WHERE organization_id = ?
             AND status IN ('approved', 'sent')
             AND (xero_invoice_id IS NULL OR xero_sync_status = 'syncing')
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (organization_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_invoices_needing_reconciliation(organization_id: str) -> list:
    """Return invoices that have a Xero ID and are not already flagged as mismatch."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_sync_status,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = ?
             AND xero_invoice_id IS NOT NULL
             AND xero_sync_status != 'mismatch'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (organization_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_failed_invoices(organization_id: str) -> list:
    """Return invoices whose last Xero sync attempt failed."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, status, created_at
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'failed'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (organization_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_mismatch_invoices(organization_id: str) -> list:
    """Return invoices where reconciliation detected a mismatch with Xero."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, created_at
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'mismatch'
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (organization_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_stale_cogs_invoices(organization_id: str) -> list:
    """Return synced invoices whose COGS journal needs to be re-posted.

    These are invoices that have a xero_invoice_id but xero_sync_status = 'cogs_stale',
    set when line items are edited after an initial successful sync.
    """
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT id, invoice_number, billing_entity, total, xero_invoice_id, xero_cogs_journal_id,
                  (SELECT COUNT(*) FROM invoice_line_items WHERE invoice_id = invoices.id) AS line_count
           FROM invoices
           WHERE organization_id = ?
             AND xero_sync_status = 'cogs_stale'
             AND xero_invoice_id IS NOT NULL
             AND deleted_at IS NULL
           ORDER BY created_at""",
        (organization_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_draft(invoice_id: str, organization_id: str | None = None) -> bool:
    """Soft-delete draft invoice and unlink withdrawals."""
    inv = await get_by_id(invoice_id, organization_id=organization_id)
    if not inv:
        return False
    if inv.get("status") != "draft":
        raise ValueError("Can only delete draft invoices")

    now = datetime.now(UTC).isoformat()
    async with transaction() as conn:
        for wid in inv.get("withdrawal_ids", []):
            await conn.execute(
                "UPDATE withdrawals SET invoice_id = NULL, payment_status = 'unpaid' WHERE id = ?",
                (wid,),
            )
        await conn.execute("DELETE FROM invoice_withdrawals WHERE invoice_id = ?", (invoice_id,))
        await conn.execute(
            "UPDATE invoices SET status = 'deleted', deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, invoice_id),
        )
    return True


class InvoiceRepo:
    insert = staticmethod(insert)
    get_by_id = staticmethod(get_by_id)
    list_invoices = staticmethod(list_invoices)
    update = staticmethod(update)
    add_withdrawals = staticmethod(add_withdrawals)
    create_from_withdrawals = staticmethod(create_from_withdrawals)
    mark_paid_for_withdrawal = staticmethod(mark_paid_for_withdrawal)
    set_xero_invoice_id = staticmethod(set_xero_invoice_id)
    set_xero_sync_status = staticmethod(set_xero_sync_status)
    list_unsynced_invoices = staticmethod(list_unsynced_invoices)
    list_invoices_needing_reconciliation = staticmethod(list_invoices_needing_reconciliation)
    list_failed_invoices = staticmethod(list_failed_invoices)
    list_mismatch_invoices = staticmethod(list_mismatch_invoices)
    list_stale_cogs_invoices = staticmethod(list_stale_cogs_invoices)
    delete_draft = staticmethod(delete_draft)


invoice_repo = InvoiceRepo()
