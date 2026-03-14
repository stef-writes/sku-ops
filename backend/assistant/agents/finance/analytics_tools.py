"""Finance analytics tools — expose ledger dimensional queries to the agent."""

import json
import logging
from datetime import UTC, datetime, timedelta

from assistant.agents.tools.registry import register as _reg
from finance.application.ledger_analytics import (
    ar_aging,
    product_margins,
    purchase_spend,
    trend_series,
)
from finance.application.ledger_queries import (
    summary_by_billing_entity,
    summary_by_contractor,
    summary_by_department,
    summary_by_job,
)

logger = logging.getLogger(__name__)


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


async def _get_trend_series(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    group_by = args.get("group_by") or ("week" if days > 60 else "day")
    start, end = _date_range(days)
    series = await trend_series(start, end, group_by)
    return json.dumps(
        {
            "period_days": days,
            "group_by": group_by,
            "data_points": len(series),
            "series": series,
        }
    )


async def _get_ar_aging(args: dict) -> str:
    days = min(int(args.get("days") or 365), 730)
    start, end = _date_range(days)
    buckets = await ar_aging(start, end)
    total_ar = round(sum(b.get("total_ar", 0) for b in buckets), 2)
    return json.dumps(
        {
            "total_ar": total_ar,
            "entity_count": len(buckets),
            "buckets": buckets,
        }
    )


async def _get_product_margins(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    limit = min(int(args.get("limit") or 20), 50)
    start, end = _date_range(days)
    margins = await product_margins(start, end, limit)
    return json.dumps(
        {
            "period_days": days,
            "count": len(margins),
            "products": margins,
        }
    )


async def _get_department_profitability(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    start, end = _date_range(days)
    depts = await summary_by_department(start, end)
    return json.dumps(
        {
            "period_days": days,
            "department_count": len(depts),
            "departments": depts,
        }
    )


async def _get_job_profitability(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    limit = min(int(args.get("limit") or 20), 50)
    start, end = _date_range(days)
    result = await summary_by_job(start, end, limit=limit)
    return json.dumps(
        {
            "period_days": days,
            "total_jobs": result.get("total", 0),
            "all_revenue": result.get("all_revenue", 0),
            "all_cost": result.get("all_cost", 0),
            "jobs": result.get("rows", []),
        }
    )


async def _get_entity_summary(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    start, end = _date_range(days)
    entities = await summary_by_billing_entity(start, end)
    return json.dumps(
        {
            "period_days": days,
            "entity_count": len(entities),
            "entities": entities,
        }
    )


async def _get_contractor_spend(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    start, end = _date_range(days)
    contractors = await summary_by_contractor(start, end)
    return json.dumps(
        {
            "period_days": days,
            "contractor_count": len(contractors),
            "contractors": contractors,
        }
    )


async def _get_purchase_spend(args: dict) -> str:
    days = min(int(args.get("days") or 30), 365)
    start, end = _date_range(days)
    total = await purchase_spend(start, end)
    return json.dumps(
        {
            "period_days": days,
            "total_purchase_spend": total,
        }
    )


# ── Registry ──────────────────────────────────────────────────────────────────

_reg("get_trend_series", "finance_analytics", _get_trend_series)
_reg("get_ar_aging", "finance_analytics", _get_ar_aging)
_reg("get_product_margins", "finance_analytics", _get_product_margins)
_reg("get_department_profitability", "finance_analytics", _get_department_profitability)
_reg("get_job_profitability", "finance_analytics", _get_job_profitability)
_reg("get_entity_summary", "finance_analytics", _get_entity_summary)
_reg("get_contractor_spend", "finance_analytics", _get_contractor_spend)
_reg("get_purchase_spend", "finance_analytics", _get_purchase_spend)
