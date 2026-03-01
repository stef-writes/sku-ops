"""Sales and inventory report routes."""
from typing import Optional

from fastapi import APIRouter, Depends

from auth import require_role
from repositories import product_repo, withdrawal_repo

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000
    )

    total_revenue = sum(w.get("total", 0) for w in withdrawals)
    total_tax = sum(w.get("tax", 0) for w in withdrawals)
    total_transactions = len(withdrawals)

    by_status = {}
    for w in withdrawals:
        status = w.get("payment_status", "unknown")
        by_status[status] = by_status.get(status, 0) + w.get("total", 0)

    product_sales = {}
    for w in withdrawals:
        for item in w.get("items", []):
            pid = item.get("product_id")
            if pid:
                if pid not in product_sales:
                    product_sales[pid] = {"name": item.get("name"), "quantity": 0, "revenue": 0}
                product_sales[pid]["quantity"] += item.get("quantity", 0)
                product_sales[pid]["revenue"] += item.get("subtotal", 0)

    top_products = sorted(product_sales.values(), key=lambda x: x["revenue"], reverse=True)[:10]

    return {
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "total_transactions": total_transactions,
        "average_transaction": round(total_revenue / total_transactions, 2) if total_transactions > 0 else 0,
        "by_payment_status": by_status,
        "top_products": top_products,
    }


@router.get("/inventory")
async def get_inventory_report(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    products = await product_repo.list_products()

    total_products = len(products)
    total_value = sum(p.get("price", 0) * p.get("quantity", 0) for p in products)
    total_cost = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]

    by_department = {}
    for p in products:
        dept = p.get("department_name", "Unknown")
        if dept not in by_department:
            by_department[dept] = {"count": 0, "value": 0}
        by_department[dept]["count"] += 1
        by_department[dept]["value"] += p.get("price", 0) * p.get("quantity", 0)

    return {
        "total_products": total_products,
        "total_retail_value": round(total_value, 2),
        "total_cost_value": round(total_cost, 2),
        "potential_profit": round(total_value - total_cost, 2),
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_items": low_stock[:20],
        "by_department": by_department,
    }
