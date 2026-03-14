"""Unified orchestrator agent — all domain tools + sub-agent delegation.

Single entry point for all chat messages. The LLM decides which tools to call,
including delegating complex analytical tasks to specialist sub-agents.
"""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.messages import build_message_history
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.runner import run_specialist
from assistant.agents.core.tokens import budget_tool_result
from assistant.agents.finance.analytics_tools import (
    _get_ar_aging,
    _get_contractor_spend,
    _get_department_profitability,
    _get_entity_summary,
    _get_job_profitability,
    _get_product_margins,
    _get_purchase_spend,
    _get_trend_series,
)
from assistant.agents.finance.tools import (
    _get_invoice_summary,
    _get_outstanding_balances,
    _get_pl_summary,
    _get_revenue_summary,
)
from assistant.agents.finance.tools import (
    _get_top_products as _get_finance_top_products,
)
from assistant.agents.health_analyst import agent as _health_agent_mod
from assistant.agents.inventory.tools import (
    _forecast_stockout,
    _get_department_activity,
    _get_department_health,
    _get_inventory_stats,
    _get_product_details,
    _get_reorder_suggestions,
    _get_slow_movers,
    _get_top_products,
    _get_usage_velocity,
    _list_departments,
    _list_low_stock,
    _list_vendors,
    _search_jobs_semantic,
    _search_pos_semantic,
    _search_products,
    _search_semantic,
    _search_vendors_semantic,
)
from assistant.agents.ops.tools import (
    _get_contractor_history,
    _get_daily_withdrawal_activity,
    _get_job_materials,
    _get_payment_status_breakdown,
    _list_pending_material_requests,
    _list_recent_withdrawals,
)
from assistant.agents.procurement_analyst import agent as _procurement_agent_mod
from assistant.agents.purchasing.tools import (
    _get_po_summary,
    _get_purchase_history,
    _get_reorder_with_vendor_context,
    _get_sku_vendor_options,
    _get_vendor_catalog,
    _get_vendor_performance,
    _list_all_vendors,
)
from assistant.agents.trend_analyst import agent as _trend_agent_mod
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:unified"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    model_settings={"temperature": 0},
)


# ── Inventory tools ───────────────────────────────────────────────────────────


@_agent.tool
async def search_products(ctx: RunContext[AgentDeps], query: str, limit: int = 20) -> str:
    """Search products by name, SKU, or barcode."""
    return budget_tool_result(await _search_products({"query": query, "limit": limit}))


@_agent.tool
async def search_semantic(ctx: RunContext[AgentDeps], query: str, limit: int = 10) -> str:
    """Semantic/concept search for products. Use when exact search fails or query is descriptive."""
    return budget_tool_result(await _search_semantic({"query": query, "limit": limit}))


@_agent.tool
async def get_product_details(ctx: RunContext[AgentDeps], sku: str) -> str:
    """Get full details for one product by SKU: price, cost, vendor, UOM, barcode, reorder point."""
    return budget_tool_result(await _get_product_details({"sku": sku}))


@_agent.tool
async def get_inventory_stats(ctx: RunContext[AgentDeps]) -> str:
    """Catalogue summary: total_skus, total_cost_value, low_stock_count, out_of_stock_count."""
    return budget_tool_result(await _get_inventory_stats())


@_agent.tool
async def list_low_stock(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """List products at or below their reorder point."""
    return budget_tool_result(await _list_low_stock({"limit": limit}))


@_agent.tool
async def list_departments(ctx: RunContext[AgentDeps]) -> str:
    """List all departments with product counts."""
    return budget_tool_result(await _list_departments())


@_agent.tool
async def list_vendors(ctx: RunContext[AgentDeps]) -> str:
    """List all vendors with product counts."""
    return budget_tool_result(await _list_vendors())


@_agent.tool
async def get_usage_velocity(ctx: RunContext[AgentDeps], sku: str, days: int = 30) -> str:
    """How fast a product moves: total and average daily withdrawals over the last N days."""
    return budget_tool_result(await _get_usage_velocity({"sku": sku, "days": days}))


@_agent.tool
async def get_reorder_suggestions(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Priority reorder list: low-stock products ranked by urgency."""
    return budget_tool_result(await _get_reorder_suggestions({"limit": limit}))


@_agent.tool
async def get_department_health(ctx: RunContext[AgentDeps]) -> str:
    """Per-department breakdown showing healthy, low-stock, and out-of-stock product counts."""
    return budget_tool_result(await _get_department_health())


@_agent.tool
async def get_slow_movers(ctx: RunContext[AgentDeps], limit: int = 20, days: int = 30) -> str:
    """Products with stock on hand but very low or zero withdrawal activity."""
    return budget_tool_result(await _get_slow_movers({"limit": limit, "days": days}))


@_agent.tool
async def get_top_products(
    ctx: RunContext[AgentDeps], days: int = 30, by: str = "revenue", limit: int = 10
) -> str:
    """Top products ranked by units withdrawn or revenue generated. by: 'volume' or 'revenue'."""
    return budget_tool_result(await _get_top_products({"days": days, "by": by, "limit": limit}))


@_agent.tool
async def get_department_activity(
    ctx: RunContext[AgentDeps], dept_code: str, days: int = 30
) -> str:
    """Stock movement summary for a department over the last N days."""
    return budget_tool_result(
        await _get_department_activity({"dept_code": dept_code, "days": days}),
    )


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 15) -> str:
    """Products predicted to run out soonest based on recent withdrawal velocity."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}))


# ── Operations tools ──────────────────────────────────────────────────────────


@_agent.tool
async def get_contractor_history(ctx: RunContext[AgentDeps], name: str, limit: int = 20) -> str:
    """Withdrawal history for a contractor (by name). Shows jobs, materials pulled, amounts."""
    return budget_tool_result(await _get_contractor_history({"name": name, "limit": limit}))


@_agent.tool
async def get_job_materials(ctx: RunContext[AgentDeps], job_id: str) -> str:
    """All materials pulled for a specific job ID."""
    return budget_tool_result(await _get_job_materials({"job_id": job_id}))


@_agent.tool
async def list_recent_withdrawals(
    ctx: RunContext[AgentDeps], days: int = 7, limit: int = 20
) -> str:
    """Recent material withdrawals across all jobs."""
    return budget_tool_result(await _list_recent_withdrawals({"days": days, "limit": limit}))


@_agent.tool
async def list_pending_material_requests(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Material requests from contractors awaiting approval."""
    return budget_tool_result(await _list_pending_material_requests({"limit": limit}))


@_agent.tool
async def get_daily_withdrawal_activity(
    ctx: RunContext[AgentDeps], days: int = 30, product_id: str = ""
) -> str:
    """Daily withdrawal volume over the last N days. Optionally filter by product_id."""
    return budget_tool_result(
        await _get_daily_withdrawal_activity({"days": days, "product_id": product_id})
    )


@_agent.tool
async def get_payment_status_breakdown(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Withdrawal totals grouped by payment status (paid/invoiced/unpaid) for the period."""
    return budget_tool_result(await _get_payment_status_breakdown({"days": days}))


# ── Finance tools ─────────────────────────────────────────────────────────────


@_agent.tool
async def get_invoice_summary(ctx: RunContext[AgentDeps]) -> str:
    """Invoice counts and totals grouped by status (draft, sent, paid)."""
    return budget_tool_result(await _get_invoice_summary())


@_agent.tool
async def get_outstanding_balances(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Unpaid withdrawal balances grouped by billing entity/contractor."""
    return budget_tool_result(await _get_outstanding_balances({"limit": limit}))


@_agent.tool
async def get_revenue_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue summary for the last N days: total revenue, tax collected, transaction count."""
    return budget_tool_result(await _get_revenue_summary({"days": days}))


@_agent.tool
async def get_pl_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Profit & loss for the last N days: revenue, COGS, gross profit and margin."""
    return budget_tool_result(await _get_pl_summary({"days": days}))


@_agent.tool
async def get_finance_top_products(
    ctx: RunContext[AgentDeps], days: int = 7, limit: int = 10
) -> str:
    """Top products ranked by revenue over the last N days."""
    return budget_tool_result(await _get_finance_top_products({"days": days, "limit": limit}))


# ── Finance analytics tools ──────────────────────────────────────────────────


@_agent.tool
async def get_trend_series(
    ctx: RunContext[AgentDeps], days: int = 30, group_by: str = "day"
) -> str:
    """Revenue/cost/profit time series. group_by: 'day', 'week', or 'month'."""
    return budget_tool_result(await _get_trend_series({"days": days, "group_by": group_by}))


@_agent.tool
async def get_ar_aging(ctx: RunContext[AgentDeps], days: int = 365) -> str:
    """Accounts receivable aging buckets by billing entity (current, 1-30, 31-60, 61-90, 90+)."""
    return budget_tool_result(await _get_ar_aging({"days": days}))


@_agent.tool
async def get_product_margins(ctx: RunContext[AgentDeps], days: int = 30, limit: int = 20) -> str:
    """Per-product revenue, COGS, profit, and margin percentage."""
    return budget_tool_result(await _get_product_margins({"days": days, "limit": limit}))


@_agent.tool
async def get_department_profitability(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue, COGS, shrinkage, profit, and margin by department."""
    return budget_tool_result(await _get_department_profitability({"days": days}))


@_agent.tool
async def get_job_profitability(ctx: RunContext[AgentDeps], days: int = 30, limit: int = 20) -> str:
    """Per-job P&L: revenue, cost, profit, margin, withdrawal count."""
    return budget_tool_result(await _get_job_profitability({"days": days, "limit": limit}))


@_agent.tool
async def get_entity_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Per billing entity: AR balance, revenue, cost, profit, transaction count."""
    return budget_tool_result(await _get_entity_summary({"days": days}))


@_agent.tool
async def get_contractor_spend(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue and AR balance by contractor over the period."""
    return budget_tool_result(await _get_contractor_spend({"days": days}))


@_agent.tool
async def get_purchase_spend(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Total inventory additions from PO receipts in the period."""
    return budget_tool_result(await _get_purchase_spend({"days": days}))


# ── Purchasing tools ─────────────────────────────────────────────────────────


@_agent.tool
async def get_vendor_catalog(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = ""
) -> str:
    """SKUs supplied by a vendor with cost, lead time, MOQ, preferred status. Pass vendor_id or name."""
    return budget_tool_result(await _get_vendor_catalog({"vendor_id": vendor_id, "name": name}))


@_agent.tool
async def get_vendor_performance(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = "", days: int = 90
) -> str:
    """Vendor reliability: PO count, total spend, avg lead time, fill rate. Pass vendor_id or name."""
    return budget_tool_result(
        await _get_vendor_performance({"vendor_id": vendor_id, "name": name, "days": days})
    )


@_agent.tool
async def get_sku_vendor_options(ctx: RunContext[AgentDeps], sku_id: str) -> str:
    """All vendors that supply a specific SKU with cost, lead time, MOQ, preferred, last PO date."""
    return budget_tool_result(await _get_sku_vendor_options({"sku_id": sku_id}))


@_agent.tool
async def get_purchase_history(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = "", days: int = 90, limit: int = 20
) -> str:
    """Recent purchase orders for a vendor with items, costs, status. Pass vendor_id or name."""
    return budget_tool_result(
        await _get_purchase_history(
            {
                "vendor_id": vendor_id,
                "name": name,
                "days": days,
                "limit": limit,
            }
        )
    )


@_agent.tool
async def get_po_summary(ctx: RunContext[AgentDeps]) -> str:
    """Purchase order counts and totals grouped by status (ordered/partial/received)."""
    return budget_tool_result(await _get_po_summary())


@_agent.tool
async def get_reorder_with_vendor_context(ctx: RunContext[AgentDeps], limit: int = 30) -> str:
    """Low-stock SKUs with vendor options (cost, lead time, preferred vendor) for procurement planning."""
    return budget_tool_result(await _get_reorder_with_vendor_context({"limit": limit}))


@_agent.tool
async def list_all_vendors_detail(ctx: RunContext[AgentDeps]) -> str:
    """All vendors with ID, name, contact, email, phone."""
    return budget_tool_result(await _list_all_vendors())


# ── Semantic search tools (multi-entity) ──────────────────────────────────────


@_agent.tool
async def search_vendors_semantic(ctx: RunContext[AgentDeps], query: str, limit: int = 10) -> str:
    """Find vendors by concept/description. Use when looking for 'that plumbing supplier' or similar."""
    return budget_tool_result(await _search_vendors_semantic({"query": query, "limit": limit}))


@_agent.tool
async def search_purchase_orders_semantic(
    ctx: RunContext[AgentDeps], query: str, limit: int = 10
) -> str:
    """Find purchase orders by concept. Use when looking for 'that PO from last quarter with issues'."""
    return budget_tool_result(await _search_pos_semantic({"query": query, "limit": limit}))


@_agent.tool
async def search_jobs_semantic(ctx: RunContext[AgentDeps], query: str, limit: int = 10) -> str:
    """Find jobs by concept. Use when looking for 'that big job on Main Street'."""
    return budget_tool_result(await _search_jobs_semantic({"query": query, "limit": limit}))


# ── Sub-agent delegation tools ────────────────────────────────────────────────


@_agent.tool
async def analyze_procurement(ctx: RunContext[AgentDeps], question: str) -> str:
    """Delegate to the procurement analyst for reorder optimization, vendor selection, cost comparison, and order grouping. Pass a clear question about what to order, which vendors to use, or how to optimize purchasing."""
    return await _procurement_agent_mod.run(question, deps=ctx.deps)


@_agent.tool
async def analyze_trends(ctx: RunContext[AgentDeps], question: str) -> str:
    """Delegate to the trend analyst for time series analysis, anomaly detection, and period-over-period comparison. Pass a question about trends, growth, changes, or what's different compared to a prior period."""
    return await _trend_agent_mod.run(question, deps=ctx.deps)


@_agent.tool
async def assess_business_health(ctx: RunContext[AgentDeps], question: str) -> str:
    """Delegate to the business health analyst for a holistic assessment across inventory, finance, and operations. Pass a question about overall business health, what needs attention, or a comprehensive review."""
    return await _health_agent_mod.run(question, deps=ctx.deps)


# ── Entry point ───────────────────────────────────────────────────────────────


async def run(
    user_message: str,
    history: list[dict] | None,
    deps: AgentDeps,
    session_id: str = "",
) -> dict:
    return await run_specialist(
        _agent,
        user_message,
        msg_history=build_message_history(history),
        deps=deps,
        agent_name="UnifiedAgent",
        agent_label="unified",
        session_id=session_id,
        history=history,
    )
