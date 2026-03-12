"""Chat assistant route — HTTP fallback for when WebSocket is unavailable.

The primary chat path is the WebSocket endpoint at /api/ws/chat which provides
real-time token streaming. This POST endpoint is the fallback for environments
where WebSocket connections are unreliable (e.g. some corporate proxies).
"""

import asyncio
import uuid

from fastapi import APIRouter

from assistant.api.schemas import ChatRequest
from assistant.application import session_store
from assistant.application.assistant import chat, recall_memory, schedule_memory_extraction
from shared.api.deps import AdminDep
from shared.infrastructure.config import (
    ANTHROPIC_AVAILABLE,
    LLM_SETUP_URL,
    OPENROUTER_AVAILABLE,
    SESSION_COST_CAP,
)

router = APIRouter(tags=["chat"])


@router.get("/chat/status")
async def chat_status(_current_user: AdminDep):
    """Return whether AI assistant is configured. Frontend can show setup prompt when false."""
    available = ANTHROPIC_AVAILABLE or OPENROUTER_AVAILABLE
    return {
        "available": available,
        "provider": "anthropic"
        if ANTHROPIC_AVAILABLE
        else "openrouter"
        if OPENROUTER_AVAILABLE
        else None,
        "setup_url": LLM_SETUP_URL if not available else None,
    }


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def clear_session(session_id: str, current_user: AdminDep):
    """Clear a chat session's history. Triggers background memory extraction first."""
    history = await session_store.get_or_create(session_id)
    if len(history) >= 4:
        schedule_memory_extraction(
            user_id=current_user.id,
            session_id=session_id,
            history=history,
        )
    await session_store.clear(session_id)


@router.post("/chat")
async def chat_assistant(
    data: ChatRequest,
    current_user: AdminDep,
):
    """Chat with AI assistant. Routes to specialist agents: inventory, ops, finance."""
    session_id = data.session_id or str(uuid.uuid4())
    user_id = current_user.id
    org_id = current_user.organization_id
    history = await session_store.get_or_create(session_id)

    if SESSION_COST_CAP > 0 and await session_store.get_cost(session_id) >= SESSION_COST_CAP:
        return {
            "response": (
                f"This session has reached the ${SESSION_COST_CAP:.2f} AI spend limit. "
                "Start a new chat to continue."
            ),
            "tool_calls": [],
            "thinking": [],
            "agent": None,
            "session_id": session_id,
            "usage": {"cost_usd": 0, "capped": True},
        }

    if not history:
        memory_ctx = await recall_memory(user_id=user_id)
        if memory_ctx:
            history = [
                {"role": "user", "content": memory_ctx},
                {"role": "assistant", "content": "Context noted from previous sessions."},
            ]

    ctx = {
        "org_id": org_id,
        "user_id": user_id,
        "user_name": current_user.name,
    }

    try:
        result = await asyncio.wait_for(
            chat(
                (data.message or "").strip(),
                history=history,
                ctx=ctx,
                agent_type=data.agent_type,
                session_id=session_id,
            ),
            timeout=120,
        )
    except TimeoutError:
        return {
            "response": "The AI assistant took too long to respond. Please try again.",
            "tool_calls": [],
            "thinking": [],
            "agent": None,
            "session_id": session_id,
            "usage": {"cost_usd": 0, "timed_out": True},
        }

    agent_history = result.pop("history", [])
    turn_cost = result.get("usage", {}).get("cost_usd", 0.0)

    # Specialist agents return full updated history; shortcut paths (trivial,
    # lookup, DAG) return [] because they don't manage conversation state.
    # In that case, preserve the existing session and append the new turn.
    if agent_history:
        new_history = agent_history
    else:
        new_history = list(history or [])
        new_history.append({"role": "user", "content": (data.message or "").strip()})
        new_history.append({"role": "assistant", "content": result.get("response", "")})

    await session_store.update(session_id, new_history, cost_usd=turn_cost)

    # Background memory extraction every 4 turns (8 messages = 4 user+assistant pairs)
    if len(new_history) % 8 == 0:
        schedule_memory_extraction(
            user_id=user_id,
            session_id=session_id,
            history=new_history,
        )

    result["session_id"] = session_id
    result["usage"] = {
        **result.get("usage", {}),
        "session_cost_usd": await session_store.get_cost(session_id),
    }
    return result
