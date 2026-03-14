"""Business health analyst sub-agent — holistic assessment across all domains."""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.tokens import budget_tool_result
from assistant.agents.finance.analytics_tools import (
    _get_ar_aging,
    _get_department_profitability,
    _get_product_margins,
)
from assistant.agents.finance.tools import (
    _get_outstanding_balances,
    _get_pl_summary,
)
from assistant.agents.inventory.tools import (
    _forecast_stockout,
    _get_department_health,
    _get_inventory_stats,
    _get_slow_movers,
    _list_low_stock,
)
from assistant.agents.ops.tools import (
    _get_payment_status_breakdown,
    _list_pending_material_requests,
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
async def get_inventory_stats(ctx: RunContext[AgentDeps]) -> str:
    """Catalogue summary: SKU count, cost value, low/out-of-stock counts."""
    return budget_tool_result(await _get_inventory_stats())


@_agent.tool
async def get_department_health(ctx: RunContext[AgentDeps]) -> str:
    """Per-department healthy/low/out-of-stock product counts."""
    return budget_tool_result(await _get_department_health())


@_agent.tool
async def list_low_stock(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Products at or below reorder point."""
    return budget_tool_result(await _list_low_stock({"limit": limit}))


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 15) -> str:
    """Products predicted to run out soonest."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}))


@_agent.tool
async def get_slow_movers(ctx: RunContext[AgentDeps], limit: int = 20, days: int = 30) -> str:
    """Dead or slow-moving stock tying up inventory."""
    return budget_tool_result(await _get_slow_movers({"limit": limit, "days": days}))


@_agent.tool
async def get_pl_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue, COGS, gross profit and margin."""
    return budget_tool_result(await _get_pl_summary({"days": days}))


@_agent.tool
async def get_outstanding_balances(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Unpaid balances by billing entity."""
    return budget_tool_result(await _get_outstanding_balances({"limit": limit}))


@_agent.tool
async def get_ar_aging(ctx: RunContext[AgentDeps], days: int = 365) -> str:
    """AR aging buckets by entity (current, 1-30, 31-60, 61-90, 90+)."""
    return budget_tool_result(await _get_ar_aging({"days": days}))


@_agent.tool
async def get_department_profitability(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue, COGS, shrinkage, profit, margin by department."""
    return budget_tool_result(await _get_department_profitability({"days": days}))


@_agent.tool
async def get_product_margins(ctx: RunContext[AgentDeps], days: int = 30, limit: int = 20) -> str:
    """Per-product margins."""
    return budget_tool_result(await _get_product_margins({"days": days, "limit": limit}))


@_agent.tool
async def get_payment_status_breakdown(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Totals by paid/invoiced/unpaid."""
    return budget_tool_result(await _get_payment_status_breakdown({"days": days}))


@_agent.tool
async def list_pending_material_requests(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Material requests awaiting approval."""
    return budget_tool_result(await _list_pending_material_requests({"limit": limit}))


async def run(question: str, deps: AgentDeps) -> str:
    """Run the health analyst and return text output."""
    result = await _agent.run(question, deps=deps)
    return result.output if isinstance(result.output, str) else str(result.output)
