"""Financial dashboard and export routes.

Summary reads from the financial_ledger (immutable event log).
Export still reads individual withdrawals for line-level CSV output.
"""
import asyncio
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from identity.application.auth_service import require_role
from kernel.types import CurrentUser, round_money
from operations.application.queries import list_withdrawals
from finance.application import ledger_queries as ledger_repo

router = APIRouter(prefix="/financials", tags=["financials"])


@router.get("/summary")
async def get_financial_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """P&L summary sourced from the financial ledger."""
    org_id = current_user.organization_id

    (
        accounts,
        by_department,
        by_entity_rows,
        by_contractor_rows,
        ar_aging_rows,
        counts,
    ) = await asyncio.gather(
        ledger_repo.summary_by_account(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.summary_by_department(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.summary_by_billing_entity(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.summary_by_contractor(org_id, start_date=start_date, end_date=end_date),
        ledger_repo.ar_aging(org_id),
        ledger_repo.reference_counts(org_id, start_date=start_date, end_date=end_date),
    )

    revenue = accounts.get("revenue", 0)
    cogs = accounts.get("cogs", 0)
    tax = accounts.get("tax_collected", 0)
    ar = accounts.get("accounts_receivable", 0)
    shrinkage = accounts.get("shrinkage", 0)

    gross_profit = round_money(revenue - cogs)
    margin_pct = round(gross_profit / revenue * 100, 1) if revenue > 0 else 0

    by_entity = {}
    for row in by_entity_rows:
        name = row["billing_entity"] or "Unknown"
        by_entity[name] = {
            "total": row["revenue"],
            "ar_balance": row.get("ar_balance", 0),
            "count": row.get("transaction_count", 0),
        }

    dept_dict = {}
    for row in by_department:
        dept_dict[row["department"]] = {
            "revenue": row["revenue"],
            "cost": row["cost"],
            "shrinkage": row.get("shrinkage", 0),
            "profit": row["profit"],
            "margin_pct": row["margin_pct"],
        }

    return {
        "gross_revenue": round_money(revenue),
        "returns_total": 0,
        "net_revenue": round_money(revenue),
        "total_cost": round_money(cogs),
        "gross_profit": gross_profit,
        "gross_margin_pct": margin_pct,
        "tax_collected": round_money(tax),
        "total_unpaid": round_money(ar),
        "total_paid": 0,
        "total_invoiced": 0,
        "total_credits": 0,
        "shrinkage": round_money(shrinkage),
        "transaction_count": counts.get("withdrawal", 0),
        "return_count": counts.get("return", 0),
        "by_billing_entity": by_entity,
        "by_contractor": by_contractor_rows,
        "by_department": dept_dict,
        "ar_aging": ar_aging_rows,
        "total_revenue": round_money(revenue),
        "gross_margin": gross_profit,
    }


@router.get("/export")
async def export_financials(
    format: str = "csv",
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Export financial data as CSV (line-level, from operational tables)."""
    org_id = current_user.organization_id
    withdrawals = await list_withdrawals(
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=10000,
        organization_id=org_id,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Transaction ID", "Date", "Contractor", "Company", "Billing Entity",
        "Job ID", "Service Address", "Subtotal", "Tax", "Total",
        "Cost", "Margin", "Payment Status", "Items"
    ])

    for w in withdrawals:
        items_str = "; ".join([f"{i['name']} x{i['quantity']}" for i in w.get("items", [])])
        writer.writerow([
            w.get("id", ""),
            w.get("created_at", "")[:10],
            w.get("contractor_name", ""),
            w.get("contractor_company", ""),
            w.get("billing_entity", ""),
            w.get("job_id", ""),
            w.get("service_address", ""),
            w.get("subtotal", 0),
            w.get("tax", 0),
            w.get("total", 0),
            w.get("cost_total", 0),
            round_money(w.get("total", 0) - w.get("cost_total", 0)),
            w.get("payment_status", ""),
            items_str
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=financials_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
