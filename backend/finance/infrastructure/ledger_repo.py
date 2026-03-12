"""Financial ledger repository — write path only.

Read-only report queries live in finance.application.ledger_queries,
which is the cross-context entry point for analytics consumers.
"""

from finance.domain.ledger import FinancialEntry
from shared.infrastructure.database import get_connection, get_org_id
from shared.kernel.types import round_money


async def entries_exist(reference_type: str, reference_id: str) -> bool:
    """Return True if any ledger rows already exist for this reference."""
    c = get_connection()
    org_id = get_org_id()
    params: list = [reference_type, reference_id]
    where = "WHERE reference_type = ? AND reference_id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    cursor = await c.execute(
        "SELECT 1 FROM financial_ledger " + where + " LIMIT 1",
        params,
    )
    return (await cursor.fetchone()) is not None


async def insert_entries(entries: list[FinancialEntry]) -> None:
    """Batch-insert ledger entries."""
    c = get_connection()
    org_id = get_org_id()
    for e in entries:
        await c.execute(
            """INSERT INTO financial_ledger
               (id, journal_id, account, amount, quantity, unit, unit_cost,
                department, job_id, billing_entity,
                contractor_id, vendor_name, product_id, performed_by_user_id,
                reference_type, reference_id, organization_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.id,
                e.journal_id,
                e.account.value,
                round_money(e.amount),
                e.quantity,
                e.unit,
                e.unit_cost,
                e.department,
                e.job_id,
                e.billing_entity,
                e.contractor_id,
                e.vendor_name,
                e.product_id,
                e.performed_by_user_id,
                e.reference_type.value,
                e.reference_id,
                org_id,
                e.created_at,
            ),
        )
    await c.commit()


async def get_journal(journal_id: str) -> list[dict]:
    """Return all entries for a single journal transaction."""
    conn = get_connection()
    org_id = get_org_id()
    params: list = [journal_id]
    where = "WHERE journal_id = ?"
    where += " AND organization_id = ?"
    params.append(org_id)
    cursor = await conn.execute(
        "SELECT * FROM financial_ledger " + where + " ORDER BY id",
        params,
    )
    return [dict(r) for r in await cursor.fetchall()]


async def trial_balance() -> dict[str, float]:
    """Sum all entries by account — should produce balanced totals."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT account, ROUND(SUM(amount), 2) AS balance
           FROM financial_ledger
           WHERE organization_id = ?
           GROUP BY account
           ORDER BY account""",
        (org_id,),
    )
    return {row[0]: row[1] for row in await cursor.fetchall()}
