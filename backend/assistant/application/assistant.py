"""Chat assistant entrypoint.

All messages are routed to the unified agent which handles inventory, ops, and
finance in a single context window.
"""

import asyncio
import logging

import assistant.agents.unified.agent as _unified_agent
from assistant.agents.core.deps import AgentDeps
from assistant.agents.core.tokens import compress_history
from assistant.agents.memory.extract import extract_and_save
from assistant.agents.memory.store import recall
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
) -> dict:
    """Route all messages to the unified agent."""
    if not ANTHROPIC_AVAILABLE and not OPENROUTER_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    ctx = ctx or {}
    deps = AgentDeps(
        user_id=ctx.get("user_id", ""),
        user_name=ctx.get("user_name", ""),
    )

    history = compress_history(history) or history

    result = await _unified_agent.run(
        user_message, history=history, deps=deps, session_id=session_id
    )
    result["routed_to"] = ["unified"]
    return result


# ── Memory facade (keeps agent imports out of the API layer) ──────────────────


async def recall_memory(user_id: str) -> str:
    """Return formatted memory context for session injection. Empty string if none."""
    return await recall(user_id=user_id)


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
