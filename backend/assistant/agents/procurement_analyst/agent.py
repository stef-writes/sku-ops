"""Procurement analyst sub-agent — multi-step reorder optimization and vendor selection."""

import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.tokens import budget_tool_result
from assistant.agents.inventory.tools import (
    _forecast_stockout,
    _get_reorder_suggestions,
)
from assistant.agents.purchasing.tools import (
    _get_purchase_history,
    _get_reorder_with_vendor_context,
    _get_sku_vendor_options,
    _get_vendor_catalog,
    _get_vendor_performance,
    _list_all_vendors,
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
async def get_reorder_with_vendor_context(ctx: RunContext[AgentDeps], limit: int = 30) -> str:
    """Low-stock SKUs with vendor options for procurement planning."""
    return budget_tool_result(await _get_reorder_with_vendor_context({"limit": limit}))


@_agent.tool
async def forecast_stockout(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Products predicted to run out soonest based on withdrawal velocity."""
    return budget_tool_result(await _forecast_stockout({"limit": limit}))


@_agent.tool
async def get_reorder_suggestions(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Priority reorder list ranked by urgency (days until stockout)."""
    return budget_tool_result(await _get_reorder_suggestions({"limit": limit}))


@_agent.tool
async def get_vendor_performance(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = "", days: int = 90
) -> str:
    """Vendor reliability: PO count, spend, avg lead time, fill rate."""
    return budget_tool_result(
        await _get_vendor_performance({"vendor_id": vendor_id, "name": name, "days": days})
    )


@_agent.tool
async def get_vendor_catalog(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = ""
) -> str:
    """SKUs supplied by a vendor with cost, lead time, MOQ."""
    return budget_tool_result(await _get_vendor_catalog({"vendor_id": vendor_id, "name": name}))


@_agent.tool
async def get_sku_vendor_options(ctx: RunContext[AgentDeps], sku_id: str) -> str:
    """All vendors for a SKU with comparative pricing and lead times."""
    return budget_tool_result(await _get_sku_vendor_options({"sku_id": sku_id}))


@_agent.tool
async def get_purchase_history(
    ctx: RunContext[AgentDeps], vendor_id: str = "", name: str = "", days: int = 90, limit: int = 20
) -> str:
    """Recent POs for a vendor."""
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
async def list_all_vendors(ctx: RunContext[AgentDeps]) -> str:
    """All vendors with ID and contact info."""
    return budget_tool_result(await _list_all_vendors())


async def run(question: str, deps: AgentDeps) -> str:
    """Run the procurement analyst and return text output."""
    result = await _agent.run(question, deps=deps)
    return result.output if isinstance(result.output, str) else str(result.output)
