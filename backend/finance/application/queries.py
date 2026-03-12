"""Finance application queries — safe for API and cross-context import.

API routes and other bounded contexts import from here, never from
finance.infrastructure directly. Thin delegation layer that decouples
consumers from infrastructure details.
"""

from finance.domain.credit_note import CreditNote
from finance.domain.invoice import Invoice
from finance.domain.payment import Payment
from finance.infrastructure.credit_note_repo import credit_note_repo as _credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo as _invoice_repo
from finance.infrastructure.payment_repo import payment_repo as _payment_repo

# ── Payment queries ──────────────────────────────────────────────────────────


async def list_payments(
    invoice_id: str | None = None,
    billing_entity_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Payment]:
    return await _payment_repo.list_payments(
        invoice_id=invoice_id,
        billing_entity_id=billing_entity_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


async def get_payment_by_id(payment_id: str) -> Payment | None:
    return await _payment_repo.get_by_id(payment_id)


# ── Credit note queries ───────────────────────────────────────────────────────


async def list_credit_notes(
    invoice_id: str | None = None,
    billing_entity: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[CreditNote]:
    return await _credit_note_repo.list_credit_notes(
        invoice_id=invoice_id,
        billing_entity=billing_entity,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )


async def get_credit_note_by_id(credit_note_id: str) -> CreditNote | None:
    return await _credit_note_repo.get_by_id(credit_note_id)


async def list_unsynced_credit_notes() -> list[CreditNote]:
    return await _credit_note_repo.list_unsynced_credit_notes()


async def list_mismatch_credit_notes() -> list[CreditNote]:
    return await _credit_note_repo.list_mismatch_credit_notes()


async def list_failed_credit_notes() -> list[CreditNote]:
    return await _credit_note_repo.list_failed_credit_notes()


# ── Invoice queries (Xero health) ────────────────────────────────────────────


async def list_unsynced_invoices() -> list[Invoice]:
    return await _invoice_repo.list_unsynced_invoices()


async def list_mismatch_invoices() -> list[Invoice]:
    return await _invoice_repo.list_mismatch_invoices()


async def list_failed_invoices() -> list[Invoice]:
    return await _invoice_repo.list_failed_invoices()
