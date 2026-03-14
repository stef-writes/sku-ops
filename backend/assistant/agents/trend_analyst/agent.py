"""Trend analyst sub-agent — time series analysis, anomaly detection, period comparison."""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.tokens import budget_tool_result
from assistant.agents.finance.analytics_tools import (
    _get_department_profitability,
    _get_product_margins,
    _get_trend_series,
)
from assistant.agents.inventory.tools import (
    _forecast_stockout,
    _get_slow_movers,
    _get_top_products,
)
from assistant.agents.ops.tools import (
    _get_daily_withdrawal_activity,
)
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:unified"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    model_settings={"temperature": 0},
)


@_agent.tool
async def get_trend_series(
    ctx: RunContext[AgentDeps], days: int = 30, group_by: str = "day"
) -> str:
    """Revenue/cost/profit time series. group_by: 'day', 'week', or 'month'."""
    return budget_tool_result(await _get_trend_series({"days": days, "group_by": group_by}))


@_agent.tool
async def get_daily_withdrawal_activity(
    ctx: RunContext[AgentDeps], days: int = 30, product_id: str = ""
) -> str:
    """Daily withdrawal volume over the last N days."""
    return budget_tool_result(
        await _get_daily_withdrawal_activity({"days": days, "product_id": product_id})
    )


@_agent.tool
async def get_product_margins(ctx: RunContext[AgentDeps], days: int = 30, limit: int = 20) -> str:
    """Per-product revenue, COGS, profit, and margin percentage."""
    return budget_tool_result(await _get_product_margins({"days": days, "limit": limit}))


@_agent.tool
async def get_department_profitability(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue, COGS, shrinkage, profit, and margin by department."""
    return budget_tool_result(await _get_department_profitability({"days": days}))


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 15) -> str:
    """Products predicted to run out soonest."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}))


@_agent.tool
async def get_slow_movers(ctx: RunContext[AgentDeps], limit: int = 20, days: int = 30) -> str:
    """Products with stock but very low withdrawal activity."""
    return budget_tool_result(await _get_slow_movers({"limit": limit, "days": days}))


@_agent.tool
async def get_top_products(
    ctx: RunContext[AgentDeps], days: int = 30, by: str = "revenue", limit: int = 10
) -> str:
    """Top products by volume or revenue."""
    return budget_tool_result(await _get_top_products({"days": days, "by": by, "limit": limit}))


async def run(question: str, deps: AgentDeps) -> str:
    """Run the trend analyst and return text output."""
    result = await _agent.run(question, deps=deps)
    return result.output if isinstance(result.output, str) else str(result.output)
