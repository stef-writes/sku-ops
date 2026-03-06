"""OpsAgent: contractors, withdrawals, jobs, material requests."""
import logging

from pydantic_ai import Agent, RunContext

from assistant.agents.core.config import load_agent_config
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.messages import build_message_history
from assistant.agents.core.model_registry import get_model
from assistant.agents.core.runner import build_model_settings, run_specialist
from assistant.agents.core.tokens import budget_tool_result
from shared.infrastructure.prompt_loader import load_prompt

from .tools import (
    _get_contractor_history,
    _get_job_materials,
    _list_pending_material_requests,
    _list_recent_withdrawals,
)

logger = logging.getLogger(__name__)

_config = load_agent_config("ops")

SYSTEM_PROMPT = load_prompt(__file__, "prompt.md")

_agent = Agent(
    get_model("agent:ops"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)


@_agent.tool
async def get_contractor_history(ctx: RunContext[AgentDeps], name: str, limit: int = 20) -> str:
    """Withdrawal history for a contractor (by name). Shows jobs, materials pulled, amounts."""
    return budget_tool_result(await _get_contractor_history({"name": name, "limit": limit}, ctx.deps.org_id))


@_agent.tool
async def get_job_materials(ctx: RunContext[AgentDeps], job_id: str) -> str:
    """All materials pulled for a specific job ID. Shows each item, quantity, cost."""
    return budget_tool_result(await _get_job_materials({"job_id": job_id}, ctx.deps.org_id))


@_agent.tool
async def list_recent_withdrawals(ctx: RunContext[AgentDeps], days: int = 7, limit: int = 20) -> str:
    """Recent material withdrawals across all jobs. Filter by last N days."""
    return budget_tool_result(await _list_recent_withdrawals({"days": days, "limit": limit}, ctx.deps.org_id))


@_agent.tool
async def list_pending_material_requests(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Material requests from contractors that are awaiting approval."""
    return budget_tool_result(await _list_pending_material_requests({"limit": limit}, ctx.deps.org_id))


async def run(user_message: str, history: list[dict] | None, deps: AgentDeps, mode: str = "fast", session_id: str = "") -> dict:
    model_settings = build_model_settings(_config, mode)

    return await run_specialist(
        _agent, user_message,
        msg_history=build_message_history(history), deps=deps,
        model_settings=model_settings,
        agent_name="OpsAgent", agent_label="ops",
        session_id=session_id, mode=mode, history=history,
        config=_config,
    )
