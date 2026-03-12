"""Unified assistant agent — all tools from inventory, ops, and finance in one agent.

Replaces the 3-specialist + router architecture for launch. The specialist agents
and routing infrastructure are preserved but bypassed via assistant.py.
"""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.messages import build_message_history
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.runner import run_specialist
from assistant.agents.core.tokens import budget_tool_result
from assistant.agents.finance.tools import (
    _get_invoice_summary,
    _get_outstanding_balances,
    _get_pl_summary,
    _get_revenue_summary,
)
from assistant.agents.finance.tools import (
    _get_top_products as _get_finance_top_products,
)

# Tool implementations from existing specialist agents
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
    _search_products,
    _search_semantic,
)
from assistant.agents.ops.tools import (
    _get_contractor_history,
    _get_job_materials,
    _list_pending_material_requests,
    _list_recent_withdrawals,
)
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:unified"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
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
    return budget_tool_result(await _get_product_details({"sku": sku}), max_tokens=400)


@_agent.tool
async def get_inventory_stats(ctx: RunContext[AgentDeps]) -> str:
    """Catalogue summary: total_skus, total_cost_value, low_stock_count, out_of_stock_count."""
    return budget_tool_result(await _get_inventory_stats(), max_tokens=300)


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
    return budget_tool_result(await _get_usage_velocity({"sku": sku, "days": days}), max_tokens=300)


@_agent.tool
async def get_reorder_suggestions(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Priority reorder list: low-stock products ranked by urgency."""
    return budget_tool_result(await _get_reorder_suggestions({"limit": limit}), max_tokens=600)


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
        max_tokens=400,
    )


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 15) -> str:
    """Products predicted to run out soonest based on recent withdrawal velocity."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}), max_tokens=600)


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


# ── Finance tools ─────────────────────────────────────────────────────────────


@_agent.tool
async def get_invoice_summary(ctx: RunContext[AgentDeps]) -> str:
    """Invoice counts and totals grouped by status (draft, sent, paid)."""
    return budget_tool_result(await _get_invoice_summary(), max_tokens=300)


@_agent.tool
async def get_outstanding_balances(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Unpaid withdrawal balances grouped by billing entity/contractor."""
    return budget_tool_result(await _get_outstanding_balances({"limit": limit}))


@_agent.tool
async def get_revenue_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue summary for the last N days: total revenue, tax collected, transaction count."""
    return budget_tool_result(await _get_revenue_summary({"days": days}), max_tokens=300)


@_agent.tool
async def get_pl_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Profit & loss for the last N days: revenue, COGS, gross profit and margin."""
    return budget_tool_result(await _get_pl_summary({"days": days}), max_tokens=300)


@_agent.tool
async def get_finance_top_products(
    ctx: RunContext[AgentDeps], days: int = 7, limit: int = 10
) -> str:
    """Top products ranked by revenue over the last N days."""
    return budget_tool_result(await _get_finance_top_products({"days": days, "limit": limit}))


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
