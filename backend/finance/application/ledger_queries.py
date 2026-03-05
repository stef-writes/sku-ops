"""Ledger read queries — analytics and reporting.

Cross-context consumers import from here, never from finance.infrastructure directly.
Write operations (insert_entries, entries_exist) remain in finance.infrastructure.ledger_repo.
"""
from typing import Optional

from shared.infrastructure.database import get_connection
from shared.infrastructure.db.sql_compat import date_group_expr

# Re-export write-path helpers that some callers (tests, ledger_service) need via this module.
from finance.infrastructure.ledger_repo import get_journal, trial_balance  # noqa: F401


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
        f"""SELECT fl.contractor_id,
                   COALESCE(MAX(u.name), '') AS name,
                   COALESCE(MAX(u.company), '') AS company,
                   ROUND(SUM(CASE WHEN fl.account = 'revenue' THEN fl.amount ELSE 0 END), 2) AS revenue,
                   ROUND(SUM(CASE WHEN fl.account = 'accounts_receivable' THEN fl.amount ELSE 0 END), 2) AS ar_balance,
                   COUNT(DISTINCT fl.reference_id) AS transaction_count
            FROM financial_ledger fl
            LEFT JOIN users u ON u.id = fl.contractor_id
            WHERE fl.organization_id = ?
              AND fl.contractor_id IS NOT NULL
              {date_filter.replace('created_at', 'fl.created_at')}
            GROUP BY fl.contractor_id""",
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


async def ar_aging(org_id: str) -> list[dict]:
    """AR aging buckets by billing entity based on invoice due_date."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT fl.billing_entity,
                  ROUND(SUM(fl.amount), 2) AS total_ar,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) <= 0 THEN fl.amount ELSE 0 END), 2) AS current_not_due,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) > 0
                                  AND julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) <= 30 THEN fl.amount ELSE 0 END), 2) AS overdue_1_30,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) > 30
                                  AND julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) <= 60 THEN fl.amount ELSE 0 END), 2) AS overdue_31_60,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) > 60
                                  AND julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) <= 90 THEN fl.amount ELSE 0 END), 2) AS overdue_61_90,
                  ROUND(SUM(CASE WHEN julianday('now') - julianday(COALESCE(inv.due_date, datetime(fl.created_at, '+30 days'))) > 90 THEN fl.amount ELSE 0 END), 2) AS overdue_90_plus
           FROM financial_ledger fl
           LEFT JOIN invoice_withdrawals iw ON fl.reference_id = iw.withdrawal_id AND fl.reference_type = 'withdrawal'
           LEFT JOIN invoices inv ON iw.invoice_id = inv.id
           WHERE fl.organization_id = ?
             AND fl.account = 'accounts_receivable'
             AND fl.billing_entity IS NOT NULL
           GROUP BY fl.billing_entity
           HAVING ROUND(SUM(fl.amount), 2) != 0""",
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
