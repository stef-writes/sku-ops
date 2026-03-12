"""Ledger analytics — time series, AR aging, product margins, purchase analytics.

Split from ledger_queries.py for file-size discipline. All functions are
re-exported from ledger_queries so existing callers are unaffected.
"""

from shared.infrastructure.database import get_connection, get_org_id
from shared.infrastructure.db.sql_compat import (
    date_add_days_expr,
    date_group_expr,
    days_overdue_expr,
)


def _build_dimension_filter(
    params: list,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
    col_prefix: str = "",
) -> str:
    """Append optional WHERE clauses for dimension drill-down filtering."""
    sql = ""
    p = col_prefix + "." if col_prefix else ""
    if job_id:
        sql += " AND " + p + "job_id = ?"
        params.append(job_id)
    if department:
        sql += " AND " + p + "department = ?"
        params.append(department)
    if billing_entity:
        sql += " AND " + p + "billing_entity = ?"
        params.append(billing_entity)
    return sql


async def trend_series(
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "day",
    *,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> list[dict]:
    """Time-series of revenue, cost, profit."""
    conn = get_connection()
    period_expr = date_group_expr("created_at", group_by)
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)
    dim_filter = _build_dimension_filter(
        params, job_id=job_id, department=department, billing_entity=billing_entity
    )

    query = "SELECT "
    query += period_expr
    query += (
        " AS period,"
        " ROUND(CAST(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END) AS NUMERIC), 2) AS cost,"
        " ROUND(CAST(SUM(CASE WHEN account = 'shrinkage' THEN amount ELSE 0 END) AS NUMERIC), 2) AS shrinkage,"
        " COUNT(DISTINCT reference_id) AS transaction_count"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND account IN ('revenue', 'cogs', 'shrinkage')"
    )
    query += date_filter + dim_filter
    query += " GROUP BY period ORDER BY period"
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    series = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost - row["shrinkage"], 2)
        series.append(
            {
                "date": row["period"],
                "revenue": revenue,
                "cost": cost,
                "shrinkage": row["shrinkage"],
                "profit": profit,
                "transaction_count": row["transaction_count"],
            }
        )
    return series


async def ar_aging(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """AR aging buckets by billing entity based on invoice due_date."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND fl.created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND fl.created_at <= ?"
        params.append(end_date)

    fallback = date_add_days_expr("fl.created_at", 30)
    due = f"COALESCE(inv.due_date, {fallback})"
    age = days_overdue_expr(due)

    query = (
        "SELECT fl.billing_entity,"
        " ROUND(CAST(SUM(fl.amount) AS NUMERIC), 2) AS total_ar,"
        f" ROUND(CAST(SUM(CASE WHEN {age} <= 0 THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS current_not_due,"
        f" ROUND(CAST(SUM(CASE WHEN {age} > 0 AND {age} <= 30 THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS overdue_1_30,"
        f" ROUND(CAST(SUM(CASE WHEN {age} > 30 AND {age} <= 60 THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS overdue_31_60,"
        f" ROUND(CAST(SUM(CASE WHEN {age} > 60 AND {age} <= 90 THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS overdue_61_90,"
        f" ROUND(CAST(SUM(CASE WHEN {age} > 90 THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS overdue_90_plus"
        " FROM financial_ledger fl"
        " LEFT JOIN invoice_withdrawals iw ON fl.reference_id = iw.withdrawal_id AND fl.reference_type = 'withdrawal'"
        " LEFT JOIN invoices inv ON iw.invoice_id = inv.id"
        " WHERE fl.organization_id = ?"
        " AND fl.account = 'accounts_receivable'"
        " AND fl.billing_entity IS NOT NULL"
    )
    query += date_filter
    query += " GROUP BY fl.billing_entity HAVING ROUND(CAST(SUM(fl.amount) AS NUMERIC), 2) != 0"
    cursor = await conn.execute(query, params)
    return [dict(r) for r in await cursor.fetchall()]


async def product_margins(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 50,
    *,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> list[dict]:
    """Per-product revenue, COGS, profit, margin."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)
    dim_filter = _build_dimension_filter(
        params, job_id=job_id, department=department, billing_entity=billing_entity
    )

    query = (
        "SELECT product_id,"
        " ROUND(CAST(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END) AS NUMERIC), 2) AS cost"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND account IN ('revenue', 'cogs')"
        " AND product_id IS NOT NULL"
    )
    query += date_filter + dim_filter
    query += " GROUP BY product_id ORDER BY revenue DESC LIMIT ?"
    cursor = await conn.execute(query, [*params, limit])
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append(
            {
                "product_id": row["product_id"],
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
            }
        )
    return result


async def purchase_spend(
    start_date: str | None = None,
    end_date: str | None = None,
) -> float:
    """Total inventory additions from PO receipts in the period."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    query = (
        "SELECT ROUND(CAST(COALESCE(SUM(amount), 0) AS NUMERIC), 2) AS total"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND account = 'inventory'"
        " AND reference_type = 'po_receipt'"
    )
    query += date_filter
    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()
    return row[0] if row else 0.0


async def reference_counts(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, int]:
    """Count distinct references by type (withdrawal, return, etc.)."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    query = (
        "SELECT reference_type, COUNT(DISTINCT reference_id) AS cnt"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
    )
    query += date_filter
    query += " GROUP BY reference_type"
    cursor = await conn.execute(query, params)
    return {row[0]: row[1] for row in await cursor.fetchall()}
