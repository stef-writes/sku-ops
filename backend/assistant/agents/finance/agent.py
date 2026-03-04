"""FinanceAgent: invoices, payments, outstanding balances, revenue, P&L."""
import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.config import load_agent_config
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.runner import build_model_settings, run_specialist
from assistant.agents.core.messages import build_message_history
from assistant.agents.core.tokens import budget_tool_result
from shared.infrastructure.prompt_loader import load_prompt
from .tools import (
    _get_invoice_summary,
    _get_outstanding_balances,
    _get_revenue_summary,
    _get_pl_summary,
    _get_top_products,
)

logger = logging.getLogger(__name__)

_config = load_agent_config("finance")

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:finance"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)


@_agent.tool
async def get_invoice_summary(ctx: RunContext[AgentDeps]) -> str:
    """Invoice counts and totals grouped by status (draft, sent, paid)."""
    return budget_tool_result(await _get_invoice_summary(ctx.deps.org_id), max_tokens=300)


@_agent.tool
async def get_outstanding_balances(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Unpaid withdrawal balances grouped by billing entity/contractor. Shows who owes money."""
    return budget_tool_result(await _get_outstanding_balances({"limit": limit}, ctx.deps.org_id))


@_agent.tool
async def get_revenue_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue summary for the last N days: total revenue, tax collected, transaction count."""
    return budget_tool_result(await _get_revenue_summary({"days": days}, ctx.deps.org_id), max_tokens=300)


@_agent.tool
async def get_pl_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Profit & loss for the last N days: revenue, cost of goods sold, gross profit and margin."""
    return budget_tool_result(await _get_pl_summary({"days": days}, ctx.deps.org_id), max_tokens=300)


@_agent.tool
async def get_top_products(ctx: RunContext[AgentDeps], days: int = 7, limit: int = 10) -> str:
    """Top products ranked by revenue over the last N days. Use for weekly/periodic sales reports."""
    return budget_tool_result(await _get_top_products({"days": days, "limit": limit}, ctx.deps.org_id))


async def run(user_message: str, history: list[dict] | None, deps: AgentDeps, mode: str = "fast", session_id: str = "") -> dict:
    model_settings = build_model_settings(_config, mode)

    return await run_specialist(
        _agent, user_message,
        msg_history=build_message_history(history), deps=deps,
        model_settings=model_settings,
        agent_name="FinanceAgent", agent_label="finance",
        session_id=session_id, mode=mode, history=history,
        config=_config,
    )
