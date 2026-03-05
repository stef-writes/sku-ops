"""Financial ledger repository — insert entries and run aggregate queries.

All report queries hit this table with simple GROUP BY statements.
No Python loops, no loading all rows, no silent zero-defaults.
"""
from typing import List, Optional

from shared.infrastructure.database import get_connection
from shared.infrastructure.db.sql_compat import date_group_expr
from finance.domain.ledger import FinancialEntry


async def entries_exist(reference_type: str, reference_id: str, conn=None) -> bool:
    """Return True if any ledger rows already exist for this reference."""
    c = conn or get_connection()
    cursor = await c.execute(
        "SELECT 1 FROM financial_ledger WHERE reference_type = ? AND reference_id = ? LIMIT 1",
        (reference_type, reference_id),
    )
    return (await cursor.fetchone()) is not None


async def insert_entries(entries: List[FinancialEntry], conn=None) -> None:
    """Batch-insert ledger entries. Uses caller's conn if inside a transaction."""
    c = conn or get_connection()
    for e in entries:
        await c.execute(
            """INSERT INTO financial_ledger
               (id, account, amount, department, job_id, billing_entity,
                contractor_id, vendor_name, product_id,
                reference_type, reference_id, organization_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e.id, e.account.value, round(e.amount, 2),
                e.department, e.job_id, e.billing_entity,
                e.contractor_id, e.vendor_name, e.product_id,
                e.reference_type.value, e.reference_id,
                e.organization_id, e.created_at,
            ),
        )
    if conn is None:
        await c.commit()


async def summary_by_account(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, float]:
    """P&L summary: {account_name: total_amount}."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT account, ROUND(SUM(amount), 2) AS total
            FROM financial_ledger
            WHERE organization_id = ?{date_filter}
            GROUP BY account""",
        params,
    )
    return {row[0]: row[1] for row in await cursor.fetchall()}


async def summary_by_department(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Per-department revenue, cogs, shrinkage."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT department,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END), 2) AS cost,
                   ROUND(SUM(CASE WHEN account = 'shrinkage' THEN amount ELSE 0 END), 2) AS shrinkage
            FROM financial_ledger
            WHERE organization_id = ?
              AND account IN ('revenue', 'cogs', 'shrinkage')
              AND department IS NOT NULL
              {date_filter}
            GROUP BY department""",
        params,
    )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append({
            "department": row["department"],
            "revenue": revenue,
            "cost": cost,
            "shrinkage": row["shrinkage"],
            "profit": profit,
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    return result


async def summary_by_job(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Per-job P&L."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT job_id,
                   billing_entity,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END), 2) AS cost,
                   COUNT(DISTINCT reference_id) AS transaction_count
            FROM financial_ledger
            WHERE organization_id = ?
              AND account IN ('revenue', 'cogs')
              AND job_id IS NOT NULL
              {date_filter}
            GROUP BY job_id, billing_entity
            ORDER BY revenue DESC
            LIMIT ?""",
        params + [limit],
    )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append({
            "job_id": row["job_id"],
            "billing_entity": row["billing_entity"],
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
            "withdrawal_count": row["transaction_count"],
        })
    return result


async def summary_by_billing_entity(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Per-entity AR balances and revenue."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT billing_entity,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END), 2) AS cost,
                   ROUND(SUM(CASE WHEN account = 'accounts_receivable' THEN amount ELSE 0 END), 2) AS ar_balance,
                   COUNT(DISTINCT reference_id) AS transaction_count
            FROM financial_ledger
            WHERE organization_id = ?
              AND billing_entity IS NOT NULL
              {date_filter}
            GROUP BY billing_entity""",
        params,
    )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append({
            "billing_entity": row["billing_entity"],
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "ar_balance": row["ar_balance"],
            "transaction_count": row["transaction_count"],
        })
    return result


async def summary_by_contractor(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Per-contractor spend totals."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT contractor_id,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'accounts_receivable' THEN amount ELSE 0 END), 2) AS ar_balance,
                   COUNT(DISTINCT reference_id) AS transaction_count
            FROM financial_ledger
            WHERE organization_id = ?
              AND contractor_id IS NOT NULL
              {date_filter}
            GROUP BY contractor_id""",
        params,
    )
    return [dict(r) for r in await cursor.fetchall()]


async def trend_series(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "day",
) -> list[dict]:
    """Time-series of revenue, cost, profit."""
    conn = get_connection()
    period_expr = date_group_expr("created_at", group_by)
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT {period_expr} AS period,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END), 2) AS cost,
                   ROUND(SUM(CASE WHEN account = 'shrinkage' THEN amount ELSE 0 END), 2) AS shrinkage
            FROM financial_ledger
            WHERE organization_id = ?
              AND account IN ('revenue', 'cogs', 'shrinkage')
              {date_filter}
            GROUP BY period
            ORDER BY period""",
        params,
    )
    rows = await cursor.fetchall()
    series = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost - row["shrinkage"], 2)
        series.append({
            "date": row["period"],
            "revenue": revenue,
            "cost": cost,
            "shrinkage": row["shrinkage"],
            "profit": profit,
        })
    return series


async def ar_aging(
    org_id: str,
) -> list[dict]:
    """AR aging buckets by billing entity: current (0-30), 31-60, 61-90, 90+."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT billing_entity,
                  ROUND(SUM(amount), 2) AS total_ar,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(created_at) <= 30 THEN amount ELSE 0 END), 2) AS current_0_30,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(created_at) > 30
                                  AND julianday('now') - julianday(created_at) <= 60 THEN amount ELSE 0 END), 2) AS overdue_31_60,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(created_at) > 60
                                  AND julianday('now') - julianday(created_at) <= 90 THEN amount ELSE 0 END), 2) AS overdue_61_90,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(created_at) > 90 THEN amount ELSE 0 END), 2) AS overdue_90_plus
           FROM financial_ledger
           WHERE organization_id = ?
             AND account = 'accounts_receivable'
             AND billing_entity IS NOT NULL
           GROUP BY billing_entity
           HAVING ROUND(SUM(amount), 2) != 0""",
        (org_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def product_margins(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Per-product revenue, COGS, profit, margin."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT product_id,
                   ROUND(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END), 2) AS cost
            FROM financial_ledger
            WHERE organization_id = ?
              AND account IN ('revenue', 'cogs')
              AND product_id IS NOT NULL
              {date_filter}
            GROUP BY product_id
            ORDER BY revenue DESC
            LIMIT ?""",
        params + [limit],
    )
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append({
            "product_id": row["product_id"],
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    return result


async def purchase_spend(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> float:
    """Total inventory additions from PO receipts in the period."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT ROUND(COALESCE(SUM(amount), 0), 2) AS total
            FROM financial_ledger
            WHERE organization_id = ?
              AND account = 'inventory'
              AND reference_type = 'po_receipt'
              {date_filter}""",
        params,
    )
    row = await cursor.fetchone()
    return row[0] if row else 0.0


async def reference_counts(
    org_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, int]:
    """Count distinct references by type (withdrawal, return, etc.)."""
    conn = get_connection()
    params: list = [org_id]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    cursor = await conn.execute(
        f"""SELECT reference_type, COUNT(DISTINCT reference_id) AS cnt
            FROM financial_ledger
            WHERE organization_id = ?{date_filter}
            GROUP BY reference_type""",
        params,
    )
    return {row[0]: row[1] for row in await cursor.fetchall()}
