"""Chat assistant entrypoint.

All messages are routed to the unified agent which handles inventory, ops, and
finance in a single agent. The previous 4-path dispatch (trivial/lookup/DAG/specialist)
is preserved below but not used — kept for reference and potential re-enablement.
"""

import asyncio
import importlib
import json
import logging

from pydantic_ai import Agent as SynthAgent

import assistant.agents.unified.agent as _unified_agent
from assistant.agents.core.contracts import AgentResult, UsageInfo
from assistant.agents.core.deps import AgentDeps
from assistant.agents.memory.extract import extract_and_save
from assistant.agents.memory.store import recall
from assistant.agents.routing.dag import execute_plan, match_report
from assistant.agents.routing.lookups import try_lookup
from assistant.agents.routing.router import classify_domain, is_trivial
from assistant.agents.tools.registry import run_tool
from assistant.infrastructure.llm import get_model
from assistant.infrastructure.llm.catalog import resolve_tier_model
from shared.infrastructure.config import (
    ANTHROPIC_AVAILABLE,
    DEFAULT_ORG_ID,
    LLM_SETUP_URL,
    OPENROUTER_AVAILABLE,
)
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_MSG = (
    "Chat assistant requires an API key. Set OPENROUTER_API_KEY (preferred) or "
    f"ANTHROPIC_API_KEY in backend/.env.  Get a key at {LLM_SETUP_URL}"
)

_AGENT_MODULES = {
    "inventory": "assistant.agents.inventory",
    "ops": "assistant.agents.ops",
    "finance": "assistant.agents.finance",
}


async def chat(
    user_message: str,
    history: list[dict] | None,
    ctx: dict | None = None,
    _agent_type: str = "auto",
    session_id: str = "",
) -> dict:
    """Route all messages to the unified agent."""
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    ctx = ctx or {}
    deps = AgentDeps(
        org_id=ctx.get("org_id", DEFAULT_ORG_ID),
        user_id=ctx.get("user_id", ""),
        user_name=ctx.get("user_name", ""),
    )

    result = await _unified_agent.run(
        user_message, history=history, deps=deps, session_id=session_id
    )
    result["routed_to"] = ["unified"]
    return result


# ── Previous 4-path dispatch — preserved but not active ──────────────────────
# To re-enable, replace the chat() body above with the logic below.


async def _chat_multipath(
    user_message: str,
    history: list[dict] | None,
    ctx: dict | None = None,
    agent_type: str = "auto",
    session_id: str = "",
) -> dict:
    """Original 4-path dispatch: trivial -> lookup -> DAG -> specialist agent. Not active."""
    ctx = ctx or {}
    deps = AgentDeps(
        org_id=ctx.get("org_id", DEFAULT_ORG_ID),
        user_id=ctx.get("user_id", ""),
        user_name=ctx.get("user_name", ""),
    )

    if agent_type != "auto":
        agent_name = agent_type if agent_type in _AGENT_MODULES else "inventory"
        return await _run_agent(agent_name, user_message, history, deps, session_id)

    if is_trivial(user_message):
        return _trivial_response(user_message)

    lookup_result = await try_lookup(user_message, deps.org_id)
    if lookup_result:
        result = AgentResult(agent="lookup", response=lookup_result)
        d = result.to_dict()
        d["routed_to"] = ["lookup"]
        return d

    report_plan = match_report(user_message)
    if report_plan:
        return await _dag_dispatch(user_message, report_plan, deps, session_id)

    agent_name = classify_domain(user_message)
    return await _run_agent(agent_name, user_message, history, deps, session_id)


# ── Trivial response (no LLM) ────────────────────────────────────────────────

_TRIVIAL_RESPONSES = {
    "hi": "Hello! How can I help you today?",
    "hello": "Hello! How can I help you today?",
    "hey": "Hey! What can I help you with?",
    "thanks": "You're welcome! Let me know if you need anything else.",
    "thank you": "You're welcome! Let me know if you need anything else.",
    "ok": "Got it. What would you like to know?",
    "okay": "Got it. What would you like to know?",
    "bye": "Goodbye! Come back anytime.",
    "goodbye": "Goodbye! Come back anytime.",
    "good morning": "Good morning! What can I help you with today?",
    "good afternoon": "Good afternoon! What can I help you with today?",
    "help": "I can help with **inventory** (products, stock, reorders), **operations** (withdrawals, contractors, jobs), and **finance** (revenue, invoices, P&L). What would you like to know?",
}


def _trivial_response(user_message: str) -> dict:
    """Return a canned response for trivial queries — zero LLM cost."""
    m = user_message.lower().strip()
    for trigger, response in _TRIVIAL_RESPONSES.items():
        if trigger in m:
            result = AgentResult(agent="system", response=response)
            d = result.to_dict()
            d["routed_to"] = ["trivial"]
            return d

    result = AgentResult(
        agent="system",
        response="Hello! I can help with inventory, operations, and finances. What would you like to know?",
    )
    d = result.to_dict()
    d["routed_to"] = ["trivial"]
    return d


# ── DAG report dispatch ───────────────────────────────────────────────────────


async def _dag_dispatch(user_message: str, plan, deps: AgentDeps, _session_id: str) -> dict:
    """Execute a structured DAG plan — parallel tool calls, cheap LLM synthesis."""
    dag_result = await execute_plan(plan, run_tool, deps.org_id)

    synth_node = plan.synthesis_node
    if synth_node and synth_node.id in dag_result.node_results:
        synth_data = dag_result.node_results[synth_node.id]
        try:
            sections = json.loads(synth_data)
        except (json.JSONDecodeError, TypeError):
            sections = {"data": synth_data}
        response = await _synthesize_dag_results(user_message, sections)
    else:
        parts = [f"**{k}**: {v}" for k, v in dag_result.node_results.items() if k != "synth"]
        response = "\n\n".join(parts)

    result = AgentResult(
        agent="dag",
        response=response,
        usage=UsageInfo(model="dag", tier="cheap"),
    )
    d = result.to_dict()
    d["routed_to"] = ["dag"]
    d["dag_template"] = plan.template_name
    return d


async def _synthesize_dag_results(query: str, sections: dict) -> str:
    """Use a cheap LLM to synthesize DAG tool results into a coherent answer."""
    try:
        model_id = resolve_tier_model("cheap")
        if not model_id:
            return _format_dag_sections(sections)

        synth = SynthAgent(
            get_model(model_id),
            system_prompt=load_prompt(__file__, "dag_synthesis_prompt.md"),
        )
        result = await asyncio.wait_for(
            synth.run(f"Question: {query}\n\nData:\n{json.dumps(sections, indent=2)}"),
            timeout=15,
        )
        return result.output if isinstance(result.output, str) else str(result.output)
    except (TimeoutError, ValueError, RuntimeError, OSError) as e:
        logger.warning("DAG synthesis failed, using raw format: %s", e)
        return _format_dag_sections(sections)


def _format_dag_sections(sections: dict) -> str:
    """Fallback formatting when LLM synthesis is unavailable."""
    parts = []
    for key, value in sections.items():
        if isinstance(value, str) and value.strip():
            parts.append(f"## {key.replace('_', ' ').title()}\n\n{value}")
    return "\n\n---\n\n".join(parts) if parts else "No data available."


# ── Agent dispatch ────────────────────────────────────────────────────────────


async def _run_agent(
    agent_name: str,
    user_message: str,
    history: list[dict] | None,
    deps: AgentDeps,
    session_id: str,
) -> dict:
    """Dispatch to a single specialist agent by name."""
    module_path = _AGENT_MODULES.get(agent_name, _AGENT_MODULES["inventory"])
    agent_module = importlib.import_module(module_path)
    result = await agent_module.run(
        user_message,
        history=history,
        deps=deps,
        session_id=session_id,
    )
    result["routed_to"] = [agent_name]
    return result


# ── Memory facade (keeps agent imports out of the API layer) ──────────────────


async def recall_memory(org_id: str, user_id: str) -> str:
    """Return formatted memory context for session injection. Empty string if none."""
    return await recall(org_id=org_id, user_id=user_id)


def schedule_memory_extraction(
    org_id: str,
    user_id: str,
    session_id: str,
    history: list[dict],
) -> None:
    """Fire-and-forget background task to extract memory artifacts from conversation."""
    asyncio.create_task(
        extract_and_save(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            history=history,
        )
    )
