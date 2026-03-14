"""Financial ledger service — writes monetary entries at event time.

Each public function corresponds to one financial event. The entries it
creates are the system of record for all reports. If an entry is wrong,
you write a correcting entry (never delete).

Every event produces a set of entries grouped under a single journal_id
so the transaction can be verified as balanced.
"""

from datetime import UTC, datetime
from uuid import uuid4

from finance.application.fiscal_period_service import check_period_open
from finance.domain.ledger import Account, FinancialEntry, ReferenceType
from finance.infrastructure.ledger_repo import entries_exist, insert_entries
from shared.infrastructure.database import get_org_id
from shared.kernel.types import round_money


async def _check_fiscal_period() -> None:
    """Check that the current date is not in a closed fiscal period."""
    now = datetime.now(UTC).isoformat()
    await check_period_open(now)


def _extract_item(item) -> tuple:
    """Extract (qty, unit, unit_price, cost, sell_cost, sell_uom, dept, product_id) from a model or dict.

    Accepts both Pydantic models (primary) and dicts (seed/test legacy).
    """
    _g = item.get if isinstance(item, dict) else lambda k, d=None: getattr(item, k, d)
    qty = _g("quantity", 0)
    unit = _g("unit", "each") or "each"
    unit_price = _g("unit_price", 0) or _g("price", 0)
    cost = _g("cost", 0)
    sell_cost = _g("sell_cost", None) or cost
    sell_uom = _g("sell_uom", None) or unit
    dept = _g("category_name", None)
    pid = _g("product_id", None)
    return qty, unit, unit_price, cost, sell_cost, sell_uom, dept, pid


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
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Shared logic for withdrawals (+1) and returns (-1).

    Entries per item: REVENUE, COGS, INVENTORY (decrease on sale, increase on return).
    Entries per event: TAX_COLLECTED, ACCOUNTS_RECEIVABLE.
    All entries share one journal_id.
    """
    if await entries_exist(reference_type.value, reference_id):
        return
    await _check_fiscal_period()
    journal_id = str(uuid4())
    common = {
        "journal_id": journal_id,
        "job_id": job_id,
        "billing_entity": billing_entity,
        "contractor_id": contractor_id,
        "performed_by_user_id": performed_by_user_id,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "organization_id": get_org_id(),
    }
    entries: list[FinancialEntry] = []

    for item in items:
        qty, unit, unit_price, _cost, sell_cost, sell_uom, dept, pid = _extract_item(item)
        entries.append(
            FinancialEntry(
                account=Account.REVENUE,
                amount=round_money(sign * unit_price * qty),
                quantity=qty,
                unit=unit,
                unit_cost=unit_price,
                department=dept,
                product_id=pid,
                **common,
            )
        )
        entries.append(
            FinancialEntry(
                account=Account.COGS,
                amount=round_money(sign * sell_cost * qty),
                quantity=qty,
                unit=sell_uom,
                unit_cost=sell_cost,
                department=dept,
                product_id=pid,
                **common,
            )
        )
        entries.append(
            FinancialEntry(
                account=Account.INVENTORY,
                amount=round_money(-sign * sell_cost * qty),
                quantity=qty,
                unit=sell_uom,
                unit_cost=sell_cost,
                department=dept,
                product_id=pid,
                **common,
            )
        )

    entries.append(
        FinancialEntry(
            account=Account.TAX_COLLECTED,
            amount=round_money(sign * tax),
            **common,
        )
    )
    entries.append(
        FinancialEntry(
            account=Account.ACCOUNTS_RECEIVABLE,
            amount=round_money(sign * total),
            **common,
        )
    )

    if created_at:
        for e in entries:
            e.created_at = created_at

    await insert_entries(entries)


async def record_withdrawal(
    withdrawal_id: str,
    items: list,
    tax: float,
    total: float,
    job_id: str,
    billing_entity: str,
    contractor_id: str,
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Write ledger entries for a new material withdrawal."""
    await _record_sale_event(
        reference_id=withdrawal_id,
        reference_type=ReferenceType.WITHDRAWAL,
        sign=+1,
        items=items,
        tax=tax,
        total=total,
        job_id=job_id,
        billing_entity=billing_entity,
        contractor_id=contractor_id,
        performed_by_user_id=performed_by_user_id,
        created_at=created_at,
    )


async def record_return(
    return_id: str,
    items: list,
    tax: float,
    total: float,
    job_id: str,
    billing_entity: str,
    contractor_id: str,
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Write reversing entries for a material return."""
    await _record_sale_event(
        reference_id=return_id,
        reference_type=ReferenceType.RETURN,
        sign=-1,
        items=items,
        tax=tax,
        total=total,
        job_id=job_id,
        billing_entity=billing_entity,
        contractor_id=contractor_id,
        performed_by_user_id=performed_by_user_id,
        created_at=created_at,
    )


async def record_po_receipt(
    po_id: str,
    items: list,
    vendor_name: str,
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Write inventory + AP entries for each received PO line item."""
    if await entries_exist(ReferenceType.PO_RECEIPT.value, po_id):
        return
    await _check_fiscal_period()
    journal_id = str(uuid4())
    org_id = get_org_id()
    entries: list[FinancialEntry] = []

    for item in items:
        cost = float(item.get("cost", 0) or 0)
        delivered = float(item.get("delivered_qty", 0) or item.get("quantity", 0) or 0)
        amount = round_money(cost * delivered)
        if amount == 0:
            continue

        base_unit = item.get("base_unit") or "each"
        dept = item.get("department") or item.get("suggested_department")
        pid = item.get("product_id")
        entries.append(
            FinancialEntry(
                account=Account.INVENTORY,
                amount=amount,
                quantity=delivered,
                unit=base_unit,
                unit_cost=cost,
                journal_id=journal_id,
                department=dept,
                vendor_name=vendor_name,
                product_id=pid,
                performed_by_user_id=performed_by_user_id,
                reference_type=ReferenceType.PO_RECEIPT,
                reference_id=po_id,
                organization_id=org_id,
            )
        )
        entries.append(
            FinancialEntry(
                account=Account.ACCOUNTS_PAYABLE,
                amount=amount,
                quantity=delivered,
                unit=base_unit,
                unit_cost=cost,
                journal_id=journal_id,
                department=dept,
                vendor_name=vendor_name,
                product_id=pid,
                performed_by_user_id=performed_by_user_id,
                reference_type=ReferenceType.PO_RECEIPT,
                reference_id=po_id,
                organization_id=org_id,
            )
        )

    if created_at:
        for e in entries:
            e.created_at = created_at
    if entries:
        await insert_entries(entries)


_DAMAGE_REASONS = {"damage"}
_THEFT_REASONS = {"theft"}


def _offset_account_for_reason(reason: str | None) -> Account:
    """Route negative adjustments to the correct contra-inventory account."""
    if reason in _DAMAGE_REASONS:
        return Account.DAMAGE
    return Account.SHRINKAGE


async def record_adjustment(
    adjustment_ref_id: str,
    product_id: str,
    product_cost: float,
    quantity_delta: float,
    department: str | None,
    reason: str | None = None,
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Write inventory + contra entries for a stock adjustment.

    Negative delta: INVENTORY decreases, offset account (shrinkage or damage) increases.
    Positive delta: INVENTORY increases, offset account decreases (found stock).
    The offset account is determined by reason: 'damage' → DAMAGE, everything else → SHRINKAGE.
    """
    if await entries_exist(ReferenceType.ADJUSTMENT.value, adjustment_ref_id):
        return
    await _check_fiscal_period()
    amount = round_money(abs(quantity_delta) * product_cost)
    if amount == 0:
        return

    org_id = get_org_id()
    journal_id = str(uuid4())
    sign = -1 if quantity_delta < 0 else 1
    offset_account = _offset_account_for_reason(reason)
    entries = [
        FinancialEntry(
            account=Account.INVENTORY,
            amount=sign * amount,
            journal_id=journal_id,
            department=department,
            product_id=product_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.ADJUSTMENT,
            reference_id=adjustment_ref_id,
            organization_id=org_id,
        ),
        FinancialEntry(
            account=offset_account,
            amount=-sign * amount,
            journal_id=journal_id,
            department=department,
            product_id=product_id,
            performed_by_user_id=performed_by_user_id,
            reference_type=ReferenceType.ADJUSTMENT,
            reference_id=adjustment_ref_id,
            organization_id=org_id,
        ),
    ]
    if created_at:
        for e in entries:
            e.created_at = created_at
    await insert_entries(entries)


async def record_payment(
    withdrawal_id: str,
    amount: float,
    billing_entity: str,
    contractor_id: str,
    performed_by_user_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Write AR reduction when a withdrawal is marked paid."""
    if await entries_exist(ReferenceType.PAYMENT.value, withdrawal_id):
        return
    journal_id = str(uuid4())
    entry = FinancialEntry(
        account=Account.ACCOUNTS_RECEIVABLE,
        amount=-round_money(amount),
        journal_id=journal_id,
        billing_entity=billing_entity,
        contractor_id=contractor_id,
        performed_by_user_id=performed_by_user_id,
        reference_type=ReferenceType.PAYMENT,
        reference_id=withdrawal_id,
        organization_id=get_org_id(),
    )
    if created_at:
        entry.created_at = created_at
    await insert_entries([entry])


async def record_credit_note_application(
    credit_note_id: str,
    amount: float,
    billing_entity: str,
    contractor_id: str,
    performed_by_user_id: str | None = None,
) -> None:
    """Write AR reduction when a credit note is applied to an invoice."""
    if await entries_exist(ReferenceType.CREDIT_NOTE.value, credit_note_id):
        return
    journal_id = str(uuid4())
    await insert_entries(
        [
            FinancialEntry(
                account=Account.ACCOUNTS_RECEIVABLE,
                amount=-round_money(amount),
                journal_id=journal_id,
                billing_entity=billing_entity,
                contractor_id=contractor_id,
                performed_by_user_id=performed_by_user_id,
                reference_type=ReferenceType.CREDIT_NOTE,
                reference_id=credit_note_id,
                organization_id=get_org_id(),
            ),
        ],
    )
