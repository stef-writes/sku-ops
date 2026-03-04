"""Financial dashboard and export routes."""
import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from identity.application.auth_service import require_role
from repositories import withdrawal_repo

router = APIRouter(prefix="/financials", tags=["financials"])


@router.get("/summary")
async def get_financial_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin")),
):
    """Get financial summary for admin dashboard"""
    org_id = current_user.get("organization_id") or "default"
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000, organization_id=org_id
    )

    total_unpaid = sum(w["total"] for w in withdrawals if w.get("payment_status") == "unpaid")
    total_paid = sum(w["total"] for w in withdrawals if w.get("payment_status") == "paid")
    total_invoiced = sum(w["total"] for w in withdrawals if w.get("payment_status") == "invoiced")
    total_revenue = sum(w["total"] for w in withdrawals)
    total_cost = sum(w.get("cost_total", 0) for w in withdrawals)

    by_entity = {}
    for w in withdrawals:
        entity = w.get("billing_entity", "Unknown")
        if entity not in by_entity:
            by_entity[entity] = {"total": 0, "unpaid": 0, "paid": 0, "count": 0}
        by_entity[entity]["total"] += w["total"]
        by_entity[entity]["count"] += 1
        if w.get("payment_status") == "unpaid":
            by_entity[entity]["unpaid"] += w["total"]
        elif w.get("payment_status") == "paid":
            by_entity[entity]["paid"] += w["total"]

    by_contractor = {}
    for w in withdrawals:
        cid = w.get("contractor_id", "Unknown")
        cname = w.get("contractor_name", "Unknown")
        if cid not in by_contractor:
            by_contractor[cid] = {"name": cname, "company": w.get("contractor_company", ""), "total": 0, "unpaid": 0, "count": 0}
        by_contractor[cid]["total"] += w["total"]
        by_contractor[cid]["count"] += 1
        if w.get("payment_status") == "unpaid":
            by_contractor[cid]["unpaid"] += w["total"]

    return {
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "gross_margin": round(total_revenue - total_cost, 2),
        "total_unpaid": round(total_unpaid, 2),
        "total_paid": round(total_paid, 2),
        "total_invoiced": round(total_invoiced, 2),
        "transaction_count": len(withdrawals),
        "by_billing_entity": by_entity,
        "by_contractor": list(by_contractor.values()),
    }


@router.get("/export")
async def export_financials(
    format: str = "csv",
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin")),
):
    """Export financial data as CSV"""
    org_id = current_user.get("organization_id") or "default"
    withdrawals = await withdrawal_repo.list_withdrawals(
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
            round(w.get("total", 0) - w.get("cost_total", 0), 2),
            w.get("payment_status", ""),
            items_str
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=financials_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
