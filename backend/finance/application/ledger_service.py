"""Financial ledger service — writes monetary entries at event time.

Each public function corresponds to one financial event. The entries it
creates are the system of record for all reports. If an entry is wrong,
you write a correcting entry (never delete).

Every event produces a set of entries grouped under a single journal_id
so the transaction can be verified as balanced.
"""
from typing import List, Optional
from uuid import uuid4

from kernel.types import round_money
from finance.domain.ledger import Account, FinancialEntry, ReferenceType
from finance.infrastructure.ledger_repo import entries_exist, insert_entries


async def _check_fiscal_period(organization_id: str) -> None:
    """Check that the current date is not in a closed fiscal period."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    try:
        from finance.api.fiscal_periods import check_period_open
        await check_period_open(now, organization_id)
    except ImportError:
        pass


def _extract_item(item) -> tuple:
    """Normalize a line item (dict or pydantic model) into (qty, unit_price, cost, dept, product_id)."""
    if isinstance(item, dict):
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price") or item.get("price", 0)
        cost = item.get("cost", 0)
        dept = item.get("department_name")
        pid = item.get("product_id")
    else:
        qty = item.quantity
        unit_price = item.unit_price
        cost = item.cost
        dept = getattr(item, "department_name", None)
        pid = item.product_id
    return qty, unit_price, cost, dept, pid


async def _record_sale_event(
    reference_id: str,
    reference_type: ReferenceType,
    sign: int,
    items: list,
    tax: float,
    total: float,
    job_id: str,
    billing_entity: str,
    contractor_id: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Shared logic for withdrawals (+1) and returns (-1).

    Entries per item: REVENUE, COGS, INVENTORY (decrease on sale, increase on return).
    Entries per event: TAX_COLLECTED, ACCOUNTS_RECEIVABLE.
    All entries share one journal_id.
    """
    if await entries_exist(reference_type.value, reference_id, conn=conn):
        return
    await _check_fiscal_period(organization_id)
    journal_id = str(uuid4())
    common = dict(
        journal_id=journal_id,
        job_id=job_id, billing_entity=billing_entity, contractor_id=contractor_id,
        performed_by_user_id=performed_by_user_id,
        reference_type=reference_type, reference_id=reference_id, organization_id=organization_id,
    )
    entries: List[FinancialEntry] = []

    for item in items:
        qty, unit_price, cost, dept, pid = _extract_item(item)
        entries.append(FinancialEntry(
            account=Account.REVENUE,
            amount=round_money(sign * unit_price * qty),
            department=dept, product_id=pid, **common,
        ))
        entries.append(FinancialEntry(
            account=Account.COGS,
            amount=round_money(sign * cost * qty),
            department=dept, product_id=pid, **common,
        ))
        entries.append(FinancialEntry(
            account=Account.INVENTORY,
            amount=round_money(-sign * cost * qty),
            department=dept, product_id=pid, **common,
        ))

    entries.append(FinancialEntry(
        account=Account.TAX_COLLECTED,
        amount=round_money(sign * tax), **common,
    ))
    entries.append(FinancialEntry(
        account=Account.ACCOUNTS_RECEIVABLE,
        amount=round_money(sign * total), **common,
    ))

    await insert_entries(entries, conn=conn)


async def record_withdrawal(
    withdrawal_id: str,
    items: list,
    tax: float,
    total: float,
    job_id: str,
    billing_entity: str,
    contractor_id: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write ledger entries for a new material withdrawal."""
    await _record_sale_event(
        reference_id=withdrawal_id,
        reference_type=ReferenceType.WITHDRAWAL,
        sign=+1,
        items=items, tax=tax, total=total,
        job_id=job_id, billing_entity=billing_entity,
        contractor_id=contractor_id, organization_id=organization_id,
        performed_by_user_id=performed_by_user_id,
        conn=conn,
    )


async def record_return(
    return_id: str,
    items: list,
    tax: float,
    total: float,
    job_id: str,
    billing_entity: str,
    contractor_id: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write reversing entries for a material return."""
    await _record_sale_event(
        reference_id=return_id,
        reference_type=ReferenceType.RETURN,
        sign=-1,
        items=items, tax=tax, total=total,
        job_id=job_id, billing_entity=billing_entity,
        contractor_id=contractor_id, organization_id=organization_id,
        performed_by_user_id=performed_by_user_id,
        conn=conn,
    )


async def record_po_receipt(
    po_id: str,
    items: list,
    vendor_name: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write inventory + AP entries for each received PO line item."""
    if await entries_exist(ReferenceType.PO_RECEIPT.value, po_id, conn=conn):
        return
    await _check_fiscal_period(organization_id)
    journal_id = str(uuid4())
    entries: List[FinancialEntry] = []

    for item in items:
        cost = float(item.get("cost", 0) or 0)
        delivered = float(item.get("delivered_qty", 0) or item.get("quantity", 0) or 0)
        amount = round_money(cost * delivered)
        if amount == 0:
            continue

        dept = item.get("department") or item.get("suggested_department")
        pid = item.get("product_id")
        entries.append(FinancialEntry(
            account=Account.INVENTORY, amount=amount,
            journal_id=journal_id,
            department=dept, vendor_name=vendor_name, product_id=pid,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.PO_RECEIPT, reference_id=po_id, organization_id=organization_id,
        ))
        entries.append(FinancialEntry(
            account=Account.ACCOUNTS_PAYABLE, amount=amount,
            journal_id=journal_id,
            department=dept, vendor_name=vendor_name, product_id=pid,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.PO_RECEIPT, reference_id=po_id, organization_id=organization_id,
        ))

    if entries:
        await insert_entries(entries, conn=conn)


async def record_adjustment(
    adjustment_ref_id: str,
    product_id: str,
    product_cost: float,
    quantity_delta: float,
    department: Optional[str],
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write inventory + shrinkage entries for a stock count adjustment.

    Negative delta = shrinkage (cost goes to shrinkage account).
    Positive delta = found stock (reverses prior shrinkage).
    """
    if await entries_exist(ReferenceType.ADJUSTMENT.value, adjustment_ref_id, conn=conn):
        return
    await _check_fiscal_period(organization_id)
    amount = round_money(abs(quantity_delta) * product_cost)
    if amount == 0:
        return

    journal_id = str(uuid4())
    sign = -1 if quantity_delta < 0 else 1
    entries = [
        FinancialEntry(
            account=Account.INVENTORY, amount=sign * amount,
            journal_id=journal_id,
            department=department, product_id=product_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.ADJUSTMENT, reference_id=adjustment_ref_id, organization_id=organization_id,
        ),
        FinancialEntry(
            account=Account.SHRINKAGE, amount=-sign * amount,
            journal_id=journal_id,
            department=department, product_id=product_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.ADJUSTMENT, reference_id=adjustment_ref_id, organization_id=organization_id,
        ),
    ]
    await insert_entries(entries, conn=conn)


async def record_payment(
    withdrawal_id: str,
    amount: float,
    billing_entity: str,
    contractor_id: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write AR reduction when a withdrawal is marked paid."""
    if await entries_exist(ReferenceType.PAYMENT.value, withdrawal_id, conn=conn):
        return
    journal_id = str(uuid4())
    await insert_entries([
        FinancialEntry(
            account=Account.ACCOUNTS_RECEIVABLE,
            amount=-round_money(amount),
            journal_id=journal_id,
            billing_entity=billing_entity,
            contractor_id=contractor_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.PAYMENT,
            reference_id=withdrawal_id,
            organization_id=organization_id,
        ),
    ], conn=conn)


async def record_credit_note_application(
    credit_note_id: str,
    amount: float,
    billing_entity: str,
    contractor_id: str,
    organization_id: str,
    performed_by_user_id: Optional[str] = None,
    conn=None,
) -> None:
    """Write AR reduction when a credit note is applied to an invoice."""
    if await entries_exist(ReferenceType.CREDIT_NOTE.value, credit_note_id, conn=conn):
        return
    journal_id = str(uuid4())
    await insert_entries([
        FinancialEntry(
            account=Account.ACCOUNTS_RECEIVABLE,
            amount=-round_money(amount),
            journal_id=journal_id,
            billing_entity=billing_entity,
            contractor_id=contractor_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.CREDIT_NOTE,
            reference_id=credit_note_id,
            organization_id=organization_id,
        ),
    ], conn=conn)
