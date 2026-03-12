"""Ledger read queries — dimension summaries and cross-context delegations.

Cross-context consumers import from here, never from finance.infrastructure directly.
Write operations (insert_entries, entries_exist) remain in finance.infrastructure.ledger_repo.

Analytics queries (trend_series, ar_aging, product_margins, purchase_spend,
reference_counts) live in ledger_analytics.py and are re-exported below.
"""

# Re-export write-path helpers that some callers (tests, ledger_service) need via this module.
# Re-export analytics so callers using `from finance.application import ledger_queries` see everything.
# _build_dimension_filter is the canonical copy (lives in ledger_analytics); imported here for local use.
from finance.application.ledger_analytics import (  # noqa: F401
    _build_dimension_filter,
    ar_aging,
    product_margins,
    purchase_spend,
    reference_counts,
    trend_series,
)
from finance.infrastructure.ledger_repo import get_journal, trial_balance  # noqa: F401
from operations.application.contractor_service import get_users_by_ids
from operations.application.queries import (
    payment_status_breakdown as _ops_pmt_status,
)
from operations.application.queries import (
    units_sold_by_product as _ops_units_sold,
)
from shared.infrastructure.database import get_connection, get_org_id


async def summary_by_account(
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
) -> dict[str, float]:
    """P&L summary: {account_name: total_amount}."""
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
        "SELECT account, ROUND(CAST(SUM(amount) AS NUMERIC), 2) AS total"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
    )
    query += date_filter + dim_filter
    query += " GROUP BY account"
    cursor = await conn.execute(query, params)
    return {row[0]: row[1] for row in await cursor.fetchall()}


async def summary_by_department(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Per-department revenue, cogs, shrinkage."""
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
        "SELECT department,"
        " ROUND(CAST(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END) AS NUMERIC), 2) AS cost,"
        " ROUND(CAST(SUM(CASE WHEN account = 'shrinkage' THEN amount ELSE 0 END) AS NUMERIC), 2) AS shrinkage"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND account IN ('revenue', 'cogs', 'shrinkage')"
        " AND department IS NOT NULL"
    )
    query += date_filter
    query += " GROUP BY department"
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append(
            {
                "department": row["department"],
                "revenue": revenue,
                "cost": cost,
                "shrinkage": row["shrinkage"],
                "profit": profit,
                "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
            }
        )
    return result


async def summary_by_job(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
) -> dict:
    """Per-job P&L with pagination and search. Returns {rows, total}."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND created_at <= ?"
        params.append(end_date)

    base = (
        "SELECT job_id,"
        " billing_entity,"
        " ROUND(CAST(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END) AS NUMERIC), 2) AS cost,"
        " COUNT(DISTINCT reference_id) AS transaction_count"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND account IN ('revenue', 'cogs')"
        " AND job_id IS NOT NULL"
    )
    base += date_filter
    base += " GROUP BY job_id, billing_entity"

    search_clause = ""
    search_params: list = []
    if search:
        term = f"%{search}%"
        search_clause = " HAVING job_id LIKE ? OR billing_entity LIKE ?"
        search_params = [term, term]

    count_query = f"SELECT COUNT(*) AS cnt, COALESCE(SUM(revenue), 0) AS total_revenue, COALESCE(SUM(cost), 0) AS total_cost FROM ({base}{search_clause})"
    count_cursor = await conn.execute(count_query, [*params, *search_params])
    agg = dict(await count_cursor.fetchone())
    total = agg["cnt"]
    all_revenue = float(agg["total_revenue"])
    all_cost = float(agg["total_cost"])

    data_query = f"{base}{search_clause} ORDER BY revenue DESC LIMIT ? OFFSET ?"
    cursor = await conn.execute(data_query, [*params, *search_params, limit, offset])
    rows = await cursor.fetchall()

    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append(
            {
                "job_id": row["job_id"],
                "billing_entity": row["billing_entity"],
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
                "withdrawal_count": row["transaction_count"],
            }
        )
    return {"rows": result, "total": total, "all_revenue": all_revenue, "all_cost": all_cost}


async def summary_by_billing_entity(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Per-entity AR balances and revenue."""
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
        "SELECT billing_entity,"
        " ROUND(CAST(SUM(CASE WHEN account = 'revenue' THEN amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN account = 'cogs' THEN amount ELSE 0 END) AS NUMERIC), 2) AS cost,"
        " ROUND(CAST(SUM(CASE WHEN account = 'accounts_receivable' THEN amount ELSE 0 END) AS NUMERIC), 2) AS ar_balance,"
        " COUNT(DISTINCT reference_id) AS transaction_count"
        " FROM financial_ledger"
        " WHERE organization_id = ?"
        " AND billing_entity IS NOT NULL"
    )
    query += date_filter
    query += " GROUP BY billing_entity"
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        row = dict(r)
        revenue = row["revenue"]
        cost = row["cost"]
        profit = round(revenue - cost, 2)
        result.append(
            {
                "billing_entity": row["billing_entity"],
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "ar_balance": row["ar_balance"],
                "transaction_count": row["transaction_count"],
            }
        )
    return result


async def summary_by_contractor(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Per-contractor spend totals."""
    conn = get_connection()
    params: list = [get_org_id()]
    date_filter = ""
    if start_date:
        date_filter += " AND fl.created_at >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND fl.created_at <= ?"
        params.append(end_date)

    query = (
        "SELECT fl.contractor_id,"
        " ROUND(CAST(SUM(CASE WHEN fl.account = 'revenue' THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS revenue,"
        " ROUND(CAST(SUM(CASE WHEN fl.account = 'accounts_receivable' THEN fl.amount ELSE 0 END) AS NUMERIC), 2) AS ar_balance,"
        " COUNT(DISTINCT fl.reference_id) AS transaction_count"
        " FROM financial_ledger fl"
        " WHERE fl.organization_id = ?"
        " AND fl.contractor_id IS NOT NULL"
    )
    query += date_filter
    query += " GROUP BY fl.contractor_id"
    cursor = await conn.execute(query, params)
    rows = [dict(r) for r in await cursor.fetchall()]

    contractor_ids = [r["contractor_id"] for r in rows]
    user_map = await get_users_by_ids(contractor_ids)

    for row in rows:
        user = user_map.get(row["contractor_id"])
        row["name"] = user.name if user else ""
        row["company"] = user.company if user else ""

    return rows


async def units_sold_by_product(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    """Delegate to operations context (owns withdrawal data)."""
    return await _ops_units_sold(start_date, end_date)


async def payment_status_breakdown(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, float]:
    """Delegate to operations context (owns withdrawal data)."""
    return await _ops_pmt_status(start_date, end_date)
