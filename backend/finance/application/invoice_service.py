"""Invoice application services — orchestration for invoice lifecycle."""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from finance.domain.invoice import InvoiceLineItem, InvoiceWithDetails, compute_due_date
from finance.infrastructure.invoice_repo import (
    insert_invoice_row,
    insert_line_items,
    link_withdrawal,
    next_invoice_number,
    replace_line_items,
    soft_delete,
    unlink_withdrawals,
    update_fields,
    update_invoice_billing,
    update_invoice_fields_dynamic,
    update_invoice_totals,
)
from finance.infrastructure.invoice_repo import (
    invoice_repo as _default_invoice_repo,
)
from finance.ports.invoice_repo_port import InvoiceRepoPort
from operations.application.queries import (
    get_withdrawal_by_id,
    link_withdrawal_to_invoice,
    unlink_withdrawals_from_invoice,
)
from shared.infrastructure.database import get_org_id, transaction
from shared.infrastructure.domain_events import dispatch
from shared.kernel.domain_events import InvoiceApproved, InvoiceCreated, InvoiceDeleted

logger = logging.getLogger(__name__)

__all__ = [
    "add_withdrawals_to_invoice",
    "approve_invoice",
    "create_invoice_from_withdrawals",
    "delete_draft_invoice",
    "get_invoice",
    "list_invoices",
    "mark_paid_for_withdrawal",
    "update_invoice",
]


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------


async def list_invoices(
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
    **kwargs,
):
    return await invoice_repo.list_invoices(**kwargs)


async def get_invoice(
    invoice_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
):
    return await invoice_repo.get_by_id(invoice_id)


async def mark_paid_for_withdrawal(
    withdrawal_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> None:
    await invoice_repo.mark_paid_for_withdrawal(withdrawal_id)


# ---------------------------------------------------------------------------
# Invoice creation from withdrawals — typed model flow
# ---------------------------------------------------------------------------


async def _validate_withdrawals_for_invoice(
    withdrawal_ids: list[str],
):
    """Fetch and validate withdrawals. Returns (withdrawals, billing_entity, contact_name)."""
    billing_entity: str | None = None
    contact_name = ""
    withdrawals: list[dict] = []

    for wid in withdrawal_ids:
        w = await get_withdrawal_by_id(wid)
        if not w:
            raise ValueError(f"Withdrawal {wid} not found")
        if w.payment_status != "unpaid":
            raise ValueError(f"Withdrawal {wid} is not unpaid")
        if w.invoice_id:
            raise ValueError(f"Withdrawal {wid} is already on invoice")
        be = w.billing_entity or ""
        if billing_entity is not None and be != billing_entity:
            raise ValueError("All withdrawals must share the same billing_entity")
        billing_entity = be
        contact_name = w.contractor_name or w.contractor_company or ""
        withdrawals.append(w)

    return withdrawals, billing_entity or "", contact_name


def _build_line_items_from_withdrawal(w, inv_id: str) -> list[dict]:
    """Convert typed WithdrawalItems to dicts for insert_line_items (repo persistence)."""
    items = []
    for item in w.items:
        line = InvoiceLineItem.from_line_item(item, invoice_id=inv_id, job_id=w.job_id)
        items.append(
            {
                "name": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "cost": line.cost,
                "product_id": line.product_id,
                "job_id": line.job_id,
                "unit": item.unit or "each",
                "sell_cost": float(item.sell_cost or item.cost),
            }
        )
    return items


async def create_invoice_from_withdrawals(
    withdrawal_ids: list[str],
) -> InvoiceWithDetails:
    """Create new invoice from unpaid withdrawals. All must share same billing_entity."""
    if not withdrawal_ids:
        raise ValueError("At least one withdrawal required")

    withdrawals, billing_entity, contact_name = await _validate_withdrawals_for_invoice(
        withdrawal_ids
    )

    inv_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    payment_terms = "net_30"
    due_date = compute_due_date(now, payment_terms)
    first_tax_rate = withdrawals[0].tax_rate if withdrawals else 0

    async with transaction():
        invoice_number = await next_invoice_number()

        await insert_invoice_row(
            inv_id=inv_id,
            invoice_number=invoice_number,
            billing_entity=billing_entity,
            contact_name=contact_name,
            contact_email="",
            tax_rate=first_tax_rate,
            payment_terms=payment_terms,
            due_date=due_date,
            now=now,
        )

        total_subtotal = 0.0
        total_tax = 0.0
        for w in withdrawals:
            items = _build_line_items_from_withdrawal(w, inv_id)
            subtotal = await insert_line_items(inv_id, items)
            total_subtotal += subtotal
            total_tax += w.tax

        total = round(total_subtotal + total_tax, 2)
        await update_invoice_totals(inv_id, total_subtotal, total_tax, total)

        for wid in withdrawal_ids:
            await link_withdrawal(inv_id, wid)
            linked = await link_withdrawal_to_invoice(wid, inv_id)
            if not linked:
                raise ValueError(f"Withdrawal {wid} was already linked to another invoice")

    await dispatch(
        InvoiceCreated(
            org_id=get_org_id(),
            invoice_id=inv_id,
            withdrawal_ids=tuple(withdrawal_ids),
        )
    )
    return await _default_invoice_repo.get_by_id(inv_id)


async def add_withdrawals_to_invoice(
    invoice_id: str,
    withdrawal_ids: list[str],
) -> InvoiceWithDetails | None:
    """Link additional withdrawals to an existing invoice."""
    if not withdrawal_ids:
        return await _default_invoice_repo.get_by_id(invoice_id)

    withdrawals, billing_entity, contact_name = await _validate_withdrawals_for_invoice(
        withdrawal_ids
    )

    inv = await _default_invoice_repo.get_by_id(invoice_id)
    if not inv:
        return None

    if inv.billing_entity and inv.billing_entity != billing_entity:
        raise ValueError("Invoice billing_entity does not match withdrawals")

    async with transaction():
        if not inv.billing_entity and billing_entity:
            await update_invoice_billing(
                invoice_id,
                billing_entity,
                contact_name or inv.contact_name,
                datetime.now(UTC).isoformat(),
            )

        total_subtotal = 0.0
        total_tax = 0.0
        for w in withdrawals:
            items = _build_line_items_from_withdrawal(w, invoice_id)
            subtotal = await insert_line_items(invoice_id, items)
            total_subtotal += subtotal
            total_tax += w.tax

        total = round(total_subtotal + total_tax, 2)
        await update_invoice_totals(invoice_id, total_subtotal, total_tax, total)

        for wid in withdrawal_ids:
            await link_withdrawal(invoice_id, wid)
            linked = await link_withdrawal_to_invoice(wid, invoice_id)
            if not linked:
                raise ValueError(f"Withdrawal {wid} was already linked to another invoice")

    return await _default_invoice_repo.get_by_id(invoice_id)


async def update_invoice(
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
    line_items: list[InvoiceLineItem] | None = None,
) -> InvoiceWithDetails | None:
    """Update invoice fields and/or replace line items."""
    inv = await _default_invoice_repo.get_by_id(invoice_id)
    if not inv:
        return None

    async with transaction():
        if line_items is not None:
            subtotal = await replace_line_items(
                invoice_id,
                [i.model_dump() if hasattr(i, "model_dump") else i for i in line_items],
            )
            tax_val = tax if tax is not None else float(inv.tax)
            total = round(subtotal + tax_val, 2)
            sync_fields: dict[str, Any] = {
                "subtotal": subtotal,
                "tax": tax_val,
                "total": total,
            }
            if inv.xero_invoice_id:
                sync_fields["xero_sync_status"] = "cogs_stale"
            await update_invoice_fields_dynamic(invoice_id, sync_fields)
        else:
            updates: dict[str, Any] = {}
            if billing_entity is not None:
                updates["billing_entity"] = billing_entity
            if contact_name is not None:
                updates["contact_name"] = contact_name
            if contact_email is not None:
                updates["contact_email"] = contact_email
            if status is not None:
                updates["status"] = status
            if notes is not None:
                updates["notes"] = notes
            if tax is not None:
                inv_subtotal = float(inv.subtotal)
                updates["tax"] = tax
                updates["total"] = round(inv_subtotal + tax, 2)
            if tax_rate is not None:
                updates["tax_rate"] = tax_rate
            if invoice_date is not None:
                updates["invoice_date"] = invoice_date
            if due_date is not None:
                updates["due_date"] = due_date
            elif payment_terms is not None:
                inv_date = invoice_date or inv.invoice_date or inv.created_at
                updates["due_date"] = compute_due_date(inv_date, payment_terms)
            if payment_terms is not None:
                updates["payment_terms"] = payment_terms
            if billing_address is not None:
                updates["billing_address"] = billing_address
            if po_reference is not None:
                updates["po_reference"] = po_reference
            await update_invoice_fields_dynamic(invoice_id, updates)

    return await _default_invoice_repo.get_by_id(invoice_id)


async def approve_invoice(invoice_id: str, approved_by_id: str) -> InvoiceWithDetails | None:
    """Approve a draft invoice, locking it for Xero sync."""
    inv = await _default_invoice_repo.get_by_id(invoice_id)
    if not inv:
        return None
    if inv.status != "draft":
        raise ValueError(f"Cannot approve invoice in '{inv.status}' status")

    now = datetime.now(UTC).isoformat()
    result = await update_fields(
        invoice_id,
        {
            "status": "approved",
            "approved_by_id": approved_by_id,
            "approved_at": now,
        },
    )
    await dispatch(InvoiceApproved(org_id=get_org_id(), invoice_id=invoice_id))
    return result


async def delete_draft_invoice(
    invoice_id: str,
) -> bool:
    """Soft-delete draft invoice and unlink withdrawals."""
    inv = await _default_invoice_repo.get_by_id(invoice_id)
    if not inv:
        return False
    if inv.status != "draft":
        raise ValueError("Can only delete draft invoices")

    async with transaction():
        wids = await unlink_withdrawals(invoice_id)
        await unlink_withdrawals_from_invoice(wids)
        await soft_delete(invoice_id)

    await dispatch(
        InvoiceDeleted(
            org_id=get_org_id(),
            invoice_id=invoice_id,
            withdrawal_ids=tuple(wids),
        )
    )
    return True
