"""Chat assistant entrypoint.

All messages are routed via the query router; specialists may handle directly
when the query clearly matches procurement, trend, or health analysis.

Context assembly pipeline enriches each request with entity graph data,
semantic memory, and session state before agent dispatch.
"""

import asyncio
import logging

import assistant.agents.health_analyst.agent as _health_agent_mod
import assistant.agents.procurement_analyst.agent as _procurement_agent_mod
import assistant.agents.trend_analyst.agent as _trend_agent_mod
import assistant.agents.unified.agent as _unified_agent
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.tokens import compress_history_async
from assistant.agents.memory.extract import extract_and_save
from assistant.agents.memory.store import recall
from assistant.application.context_assembly import assemble_context
from assistant.application.query_router import route_query
from assistant.application.session_state import SessionState
from shared.infrastructure.config import (
    ANTHROPIC_AVAILABLE,
    LLM_SETUP_URL,
    OPENROUTER_AVAILABLE,
)

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_MSG = (
    "Chat assistant requires an API key. Set OPENROUTER_API_KEY (preferred) or "
    f"ANTHROPIC_API_KEY in backend/.env.  Get a key at {LLM_SETUP_URL}"
)


async def chat(
    user_message: str,
    history: list[dict] | None,
    ctx: dict | None = None,
    agent_type: str = "auto",
    session_id: str = "",
    session_state: SessionState | None = None,
) -> dict:
    """Route message via query router; specialists handle when appropriate."""
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    ctx = ctx or {}
    user_id = ctx.get("user_id", "")
    deps = AgentDeps(
        user_id=user_id,
        user_name=ctx.get("user_name", ""),
    )

    # Progressive summarization (async) — falls back to truncation if LLM unavailable
    history = await compress_history_async(history) or history

    # Assemble rich context from entity graph, memory, and session state
    assembled = await assemble_context(
        query=user_message,
        user_id=user_id,
        session_state=session_state,
    )
    context_block = assembled.format_for_agent()
    if context_block:
        # Inject as system message at the start of history
        history = [{"role": "system", "content": context_block}] + (history or [])

    route = await route_query(user_message, history)
    logger.info("Query router: %s for message='%s...'", route, (user_message or "")[:50])

    if route == "procurement":
        response = await _procurement_agent_mod.run(user_message, deps=deps)
        return _specialist_result(user_message, response, "procurement", history or [])
    if route == "trend":
        response = await _trend_agent_mod.run(user_message, deps=deps)
        return _specialist_result(user_message, response, "trend", history or [])
    if route == "health":
        response = await _health_agent_mod.run(user_message, deps=deps)
        return _specialist_result(user_message, response, "health", history or [])

    result = await _unified_agent.run(
        user_message, history=history, deps=deps, session_id=session_id
    )
    result["routed_to"] = ["unified"]
    return result


def _specialist_result(
    user_message: str, response: str, agent_label: str, history: list[dict]
) -> dict:
    """Format specialist run output to match unified agent result shape."""
    new_history = list(history)
    new_history.append({"role": "user", "content": user_message})
    new_history.append({"role": "assistant", "content": response})
    return {
        "response": response,
        "tool_calls": [],
        "history": new_history,
        "agent": agent_label,
        "routed_to": [agent_label],
        "usage": {"cost_usd": 0, "input_tokens": 0, "output_tokens": 0, "model": ""},
    }


# ── Memory facade (keeps agent imports out of the API layer) ──────────────────


async def recall_memory(user_id: str, query: str | None = None) -> str:
    """Return formatted memory context for session injection.

    When *query* is provided, uses semantic recall (hybrid scoring).
    Returns empty string if no artifacts exist.
    """
    return await recall(user_id=user_id, query=query)


def schedule_memory_extraction(
    user_id: str,
    session_id: str,
    history: list[dict],
) -> None:
    """Fire-and-forget background task to extract memory artifacts from conversation."""
    asyncio.create_task(
        extract_and_save(
            user_id=user_id,
            session_id=session_id,
            history=history,
        )
    )
