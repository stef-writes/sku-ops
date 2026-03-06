"""Financial ledger repository — write path only.

Read-only report queries live in finance.application.ledger_queries,
which is the cross-context entry point for analytics consumers.
"""
from typing import List

from finance.domain.ledger import FinancialEntry
from kernel.types import round_money
from shared.infrastructure.database import get_connection


async def entries_exist(reference_type: str, reference_id: str, conn=None, organization_id: str | None = None) -> bool:
    """Return True if any ledger rows already exist for this reference."""
    c = conn or get_connection()
    params: list = [reference_type, reference_id]
    where = "WHERE reference_type = ? AND reference_id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    cursor = await c.execute(
        f"SELECT 1 FROM financial_ledger {where} LIMIT 1",
        params,
    )
    return (await cursor.fetchone()) is not None


async def insert_entries(entries: list[FinancialEntry], conn=None) -> None:
    """Batch-insert ledger entries. Uses caller's conn if inside a transaction."""
    c = conn or get_connection()
    for e in entries:
        await c.execute(
            """INSERT INTO financial_ledger
               (id, journal_id, account, amount, quantity, unit, unit_cost,
                department, job_id, billing_entity,
                contractor_id, vendor_name, product_id, performed_by_user_id,
                reference_type, reference_id, organization_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.id, e.journal_id, e.account.value, round_money(e.amount),
                e.quantity, e.unit, e.unit_cost,
                e.department, e.job_id, e.billing_entity,
                e.contractor_id, e.vendor_name, e.product_id,
                e.performed_by_user_id,
                e.reference_type.value, e.reference_id,
                e.organization_id, e.created_at,
            ),
        )
    if conn is None:
        await c.commit()


async def get_journal(journal_id: str, organization_id: str | None = None) -> list[dict]:
    """Return all entries for a single journal transaction."""
    conn = get_connection()
    params: list = [journal_id]
    where = "WHERE journal_id = ?"
    if organization_id:
        where += " AND organization_id = ?"
        params.append(organization_id)
    cursor = await conn.execute(
        f"SELECT * FROM financial_ledger {where} ORDER BY id",
        params,
    )
    return [dict(r) for r in await cursor.fetchall()]


async def trial_balance(org_id: str) -> dict[str, float]:
    """Sum all entries by account — should produce balanced totals."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT account, ROUND(SUM(amount), 2) AS balance
           FROM financial_ledger
           WHERE organization_id = ?
           GROUP BY account
           ORDER BY account""",
        (org_id,),
    )
    return {row[0]: row[1] for row in await cursor.fetchall()}
