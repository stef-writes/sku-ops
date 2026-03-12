"""InventoryAgent: product search, stock levels, reorders, departments, vendors."""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.config import load_agent_config
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.messages import build_message_history
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.runner import build_model_settings, run_specialist
from assistant.agents.core.tokens import budget_tool_result
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
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_config = load_agent_config("inventory")

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:inventory"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)


@_agent.tool
async def search_products(ctx: RunContext[AgentDeps], query: str, limit: int = 20) -> str:
    """Search products by name, SKU, or barcode. Returns matching products with SKU, name, quantity, min_stock, department."""
    return budget_tool_result(await _search_products({"query": query, "limit": limit}))


@_agent.tool
async def search_semantic(ctx: RunContext[AgentDeps], query: str, limit: int = 10) -> str:
    """Semantic/concept search for products. Use when exact search fails or query is descriptive (e.g. 'something for fixing pipes', 'waterproof coating')."""
    return budget_tool_result(await _search_semantic({"query": query, "limit": limit}))


@_agent.tool
async def get_product_details(ctx: RunContext[AgentDeps], sku: str) -> str:
    """Get full details for one product by SKU: price, cost, vendor, UOM, barcode, reorder point."""
    return budget_tool_result(await _get_product_details({"sku": sku}), max_tokens=400)


@_agent.tool
async def get_inventory_stats(ctx: RunContext[AgentDeps]) -> str:
    """Catalogue summary: total_skus (distinct product lines), total_cost_value, low_stock_count, out_of_stock_count. Does NOT return a meaningful total unit count — products have different units."""
    return budget_tool_result(await _get_inventory_stats(), max_tokens=300)


@_agent.tool
async def list_low_stock(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """List products at or below their reorder point (quantity <= min_stock)."""
    return budget_tool_result(await _list_low_stock({"limit": limit}))


@_agent.tool
async def list_departments(ctx: RunContext[AgentDeps]) -> str:
    """List all departments with product counts and next SKU."""
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
    """Priority reorder list: low-stock products ranked by urgency (days until stockout based on usage velocity)."""
    return budget_tool_result(await _get_reorder_suggestions({"limit": limit}), max_tokens=600)


@_agent.tool
async def get_department_health(ctx: RunContext[AgentDeps]) -> str:
    """Per-department breakdown showing healthy, low-stock, and out-of-stock product counts."""
    return budget_tool_result(await _get_department_health())


@_agent.tool
async def get_slow_movers(ctx: RunContext[AgentDeps], limit: int = 20, days: int = 30) -> str:
    """Products with stock on hand but very low or zero withdrawal activity — dead or slow-moving stock tying up inventory."""
    return budget_tool_result(await _get_slow_movers({"limit": limit, "days": days}))


@_agent.tool
async def get_top_products(
    ctx: RunContext[AgentDeps], days: int = 30, by: str = "revenue", limit: int = 10
) -> str:
    """Top products ranked by units withdrawn or revenue generated over the last N days. by: 'volume' or 'revenue'."""
    return budget_tool_result(await _get_top_products({"days": days, "by": by, "limit": limit}))


@_agent.tool
async def get_department_activity(
    ctx: RunContext[AgentDeps], dept_code: str, days: int = 30
) -> str:
    """Stock movement summary for a department over the last N days (withdrawals, receiving, net change)."""
    return budget_tool_result(
        await _get_department_activity({"dept_code": dept_code, "days": days}),
        max_tokens=400,
    )


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 15) -> str:
    """Products predicted to run out soonest based on recent withdrawal velocity. Returns days-until-zero estimates."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}), max_tokens=600)


async def run(
    user_message: str, history: list[dict] | None, deps: AgentDeps, session_id: str = ""
) -> dict:
    model_settings = build_model_settings(_config)

    return await run_specialist(
        _agent,
        user_message,
        msg_history=build_message_history(history),
        deps=deps,
        model_settings=model_settings,
        agent_name="InventoryAgent",
        agent_label="inventory",
        session_id=session_id,
        history=history,
        config=_config,
    )
