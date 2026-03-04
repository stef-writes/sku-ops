"""Chat assistant entrypoint — 4-path dispatch.

Execution paths (cheapest first):
1. Trivial  → canned response ($0)
2. Lookup   → pattern-match to single tool + template ($0)
3. Report   → DAG parallel tools + cheap synthesis ($0.001)
4. Reasoning → specialist agent with tools ($0.003-$0.015)

mode="deep" skips lookup/report shortcuts, goes straight to Sonnet agent.
"""
import asyncio
import importlib
import json
import logging

from pydantic_ai import Agent as SynthAgent

from shared.infrastructure.config import ANTHROPIC_AVAILABLE, OPENROUTER_AVAILABLE, LLM_SETUP_URL
from shared.infrastructure.prompt_loader import load_prompt
from assistant.infrastructure.llm.catalog import resolve_tier_model
from assistant.infrastructure.llm import get_model
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.contracts import AgentResult, UsageInfo
from assistant.agents.routing.router import is_trivial, classify_domain
from assistant.agents.routing.lookups import try_lookup
from assistant.agents.routing.dag import match_report, execute_plan
from assistant.agents.tools.registry import run_tool
from assistant.agents.memory.store import recall
from assistant.agents.memory.extract import extract_and_save

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_MSG = (
    "Chat assistant requires an API key. Set OPENROUTER_API_KEY (preferred) or "
    f"ANTHROPIC_API_KEY in backend/.env.  Get a key at {LLM_SETUP_URL}"
)

_AGENT_MODULES = {
    "inventory": "assistant.agents.inventory",
    "ops":       "assistant.agents.ops",
    "finance":   "assistant.agents.finance",
}


async def chat(
    user_message: str,
    history: list[dict] | None,
    ctx: dict | None = None,
    mode: str = "fast",
    agent_type: str = "auto",
    session_id: str = "",
) -> dict:
    """Dispatch user message to the cheapest correct execution path."""
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    ctx = ctx or {}
    deps = AgentDeps(
        org_id=ctx.get("org_id", "default"),
        user_id=ctx.get("user_id", ""),
        user_name=ctx.get("user_name", ""),
    )

    if agent_type != "auto":
        agent_name = agent_type if agent_type in _AGENT_MODULES else "inventory"
        return await _run_agent(agent_name, user_message, history, deps, mode, session_id)

    if mode == "deep":
        agent_name = classify_domain(user_message)
        return await _run_agent(agent_name, user_message, history, deps, mode, session_id)

    # ── Path 1: Trivial ───────────────────────────────────────────────────
    if is_trivial(user_message):
        logger.info("dispatch → trivial")
        return _trivial_response(user_message)

    # ── Path 2: Lookup (zero LLM) ────────────────────────────────────────
    lookup_result = await try_lookup(user_message, deps.org_id)
    if lookup_result:
        logger.info("dispatch → lookup")
        result = AgentResult(agent="lookup", response=lookup_result)
        d = result.to_dict()
        d["routed_to"] = ["lookup"]
        return d

    # ── Path 3: Report (DAG + cheap synthesis) ────────────────────────────
    report_plan = match_report(user_message)
    if report_plan:
        logger.info(f"dispatch → report ({report_plan.template_name})")
        return await _dag_dispatch(user_message, report_plan, deps, session_id)

    # ── Path 4: Reasoning (specialist agent) ──────────────────────────────
    agent_name = classify_domain(user_message)
    logger.info(f"dispatch → reasoning ({agent_name})")
    return await _run_agent(agent_name, user_message, history, deps, mode, session_id)


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

async def _dag_dispatch(user_message: str, plan, deps: AgentDeps, session_id: str) -> dict:
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
    except Exception as e:
        logger.warning(f"DAG synthesis failed, using raw format: {e}")
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
    mode: str,
    session_id: str,
) -> dict:
    """Dispatch to a single specialist agent by name."""
    module_path = _AGENT_MODULES.get(agent_name, _AGENT_MODULES["inventory"])
    agent_module = importlib.import_module(module_path)
    result = await agent_module.run(
        user_message, history=history, deps=deps, mode=mode, session_id=session_id,
    )
    result["routed_to"] = [agent_name]
    return result


# ── Memory facade (keeps agent imports out of the API layer) ──────────────────

async def recall_memory(org_id: str, user_id: str) -> str:
    """Return formatted memory context for session injection. Empty string if none."""
    return await recall(org_id=org_id, user_id=user_id)


def schedule_memory_extraction(
    org_id: str, user_id: str, session_id: str, history: list[dict],
) -> None:
    """Fire-and-forget background task to extract memory artifacts from conversation."""
    asyncio.create_task(extract_and_save(
        org_id=org_id, user_id=user_id, session_id=session_id, history=history,
    ))
