"""Dashboard stats routes."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

from auth import get_current_user
from repositories import product_repo, user_repo, vendor_repo, withdrawal_repo

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.isoformat()

    if current_user.get("role") == "contractor":
        my_withdrawals = await withdrawal_repo.list_withdrawals(
            contractor_id=current_user["id"], limit=1000
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
        start_date=today_str, limit=1000
    )
    today_revenue = sum(w.get("total", 0) for w in today_withdrawals)
    today_transactions = len(today_withdrawals)

    week_start = (datetime.now(timezone.utc) - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_str = week_start.isoformat()
    week_withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=week_start_str, limit=10000
    )
    week_revenue = sum(w.get("total", 0) for w in week_withdrawals)

    total_products = await product_repo.count_all()
    low_stock_products = await product_repo.count_low_stock()
    total_vendors = await vendor_repo.count()
    total_contractors = await user_repo.count_contractors()

    unpaid_withdrawals = await withdrawal_repo.list_withdrawals(
        payment_status="unpaid", limit=10000
    )
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)

    recent_withdrawals = await withdrawal_repo.list_withdrawals(limit=5)
    low_stock_items = await product_repo.list_low_stock(10)

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
