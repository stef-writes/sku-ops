"""Dashboard stats routes."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from catalog.infrastructure.product_repo import product_repo
from identity.infrastructure.user_repo import user_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.isoformat()

    org_id = current_user.get("organization_id") or "default"
    if current_user.get("role") == "contractor":
        my_withdrawals = await withdrawal_repo.list_withdrawals(
            contractor_id=current_user["id"], limit=1000, organization_id=org_id
        )

        total_spent = sum(w.get("total", 0) for w in my_withdrawals)
        unpaid = sum(w.get("total", 0) for w in my_withdrawals if w.get("payment_status") == "unpaid")

        return {
            "total_withdrawals": len(my_withdrawals),
            "total_spent": round(total_spent, 2),
            "unpaid_balance": round(unpaid, 2),
            "recent_withdrawals": my_withdrawals[:5],
        }

    today_withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=today_str, limit=1000, organization_id=org_id
    )
    today_revenue = sum(w.get("total", 0) for w in today_withdrawals)
    today_transactions = len(today_withdrawals)

    week_start = (datetime.now(timezone.utc) - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_str = week_start.isoformat()
    week_withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=week_start_str, limit=10000, organization_id=org_id
    )
    week_revenue = sum(w.get("total", 0) for w in week_withdrawals)

    total_products = await product_repo.count_all(org_id)
    low_stock_products = await product_repo.count_low_stock(org_id)
    total_vendors = await vendor_repo.count(org_id)
    total_contractors = await user_repo.count_contractors(org_id)

    unpaid_withdrawals = await withdrawal_repo.list_withdrawals(
        payment_status="unpaid", limit=10000, organization_id=org_id
    )
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)

    recent_withdrawals = await withdrawal_repo.list_withdrawals(limit=5, organization_id=org_id)
    low_stock_items = await product_repo.list_low_stock(10, org_id)

    revenue_by_day = {}
    for i in range(7):
        d = (datetime.now(timezone.utc) - timedelta(days=6 - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        key = d.strftime("%Y-%m-%d")
        revenue_by_day[key] = 0
    for w in week_withdrawals:
        created = w.get("created_at", "")[:10]
        if created in revenue_by_day:
            revenue_by_day[created] += w.get("total", 0)
    revenue_by_day_list = [{"date": k, "revenue": round(v, 2)} for k, v in sorted(revenue_by_day.items())]

    return {
        "today_revenue": round(today_revenue, 2),
        "today_transactions": today_transactions,
        "week_revenue": round(week_revenue, 2),
        "revenue_by_day": revenue_by_day_list,
        "total_products": total_products,
        "low_stock_count": low_stock_products,
        "total_vendors": total_vendors,
        "total_contractors": total_contractors,
        "unpaid_total": round(unpaid_total, 2),
        "recent_withdrawals": recent_withdrawals,
        "low_stock_alerts": low_stock_items,
    }


@router.get("/transactions")
async def get_dashboard_transactions(
    limit: int = 20,
    offset: int = 0,
    time_range: str = "24h",
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Paginated transactions for the dashboard terminal. time_range: today | 24h | 7d | all."""
    org_id = current_user.get("organization_id") or "default"
    now = datetime.now(timezone.utc)

    if time_range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = start.isoformat()
        end_date = None
    elif time_range == "24h":
        start = now - timedelta(hours=24)
        start_date = start.isoformat()
        end_date = None
    elif time_range == "7d":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = start.isoformat()
        end_date = None
    elif time_range == "all":
        start_date = None
        end_date = None
    else:
        raise HTTPException(status_code=400, detail="time_range must be today, 24h, 7d, or all")

    fetch_limit = limit + 1
    rows = await withdrawal_repo.list_withdrawals(
        start_date=start_date,
        end_date=end_date,
        limit=fetch_limit,
        offset=offset,
        organization_id=org_id,
    )
    has_more = len(rows) > limit
    withdrawals = rows[:limit]
    return {"withdrawals": withdrawals, "has_more": has_more}
