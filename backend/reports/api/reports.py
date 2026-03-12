"""Sales, inventory, and financial report routes.

Thin controllers — all computation delegated to reports/application/report_queries.py.
"""

from fastapi import APIRouter

from reports.application.report_queries import (
    ar_aging_report,
    inventory_report,
    job_pl_report,
    kpi_report,
    pl_report,
    product_activity_report,
    product_margins_report,
    product_performance_report,
    reorder_urgency_report,
    sales_report,
    trends_report,
)
from shared.api.deps import AdminDep

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def get_sales_report(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
):
    return await sales_report(
        start_date=start_date,
        end_date=end_date,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )


@router.get("/inventory")
async def get_inventory_report(current_user: AdminDep):
    return await inventory_report()


@router.get("/trends")
async def get_trends_report(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "day",
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
):
    """Revenue/cost/profit trends from the ledger."""
    return await trends_report(
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )


@router.get("/product-margins")
async def get_product_margins(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
):
    return await product_margins_report(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )


@router.get("/job-pl")
async def get_job_pl(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
):
    """Per-job P&L from the ledger."""
    return await job_pl_report(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/pl")
async def get_pl(
    current_user: AdminDep,
    group_by: str = "overall",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
):
    """Unified P&L endpoint. group_by: overall | job | contractor | department | entity | product."""
    return await pl_report(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        search=search,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )


@router.get("/ar-aging")
async def get_ar_aging(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Accounts receivable aging buckets by billing entity."""
    return await ar_aging_report(start_date=start_date, end_date=end_date)


@router.get("/kpis")
async def get_kpis(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    job_id: str | None = None,
    department: str | None = None,
    billing_entity: str | None = None,
):
    return await kpi_report(
        start_date=start_date,
        end_date=end_date,
        job_id=job_id,
        department=department,
        billing_entity=billing_entity,
    )


@router.get("/product-performance")
async def get_product_performance(
    current_user: AdminDep,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
):
    return await product_performance_report(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/reorder-urgency")
async def get_reorder_urgency(
    current_user: AdminDep,
    days: int = 30,
    limit: int = 50,
):
    """Products ranked by days-until-stockout using withdrawal velocity."""
    return await reorder_urgency_report(days=days, limit=limit)


@router.get("/product-activity")
async def get_product_activity(
    current_user: AdminDep,
    product_id: str | None = None,
    days: int = 365,
):
    """Daily withdrawal activity heatmap data. Optional product_id filter."""
    return await product_activity_report(product_id=product_id, days=days)
