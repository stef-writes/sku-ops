"""Chat assistant route."""
import asyncio
import uuid

from fastapi import APIRouter, Depends

from identity.application.auth_service import get_current_user
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL, SESSION_COST_CAP

from .schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.get("/chat/status")
async def chat_status(current_user: dict = Depends(get_current_user)):
    """Return whether AI assistant is configured. Frontend can show setup prompt when false."""
    return {
        "available": ANTHROPIC_AVAILABLE,
        "provider": "anthropic" if ANTHROPIC_AVAILABLE else None,
        "setup_url": LLM_SETUP_URL if not ANTHROPIC_AVAILABLE else None,
    }


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def clear_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Clear a chat session's history. Triggers background memory extraction first."""
    from services import session_store
    from services.agents.memory_extract import extract_and_save

    history = session_store.get_or_create(session_id)
    if len(history) >= 4:
        asyncio.create_task(extract_and_save(
            org_id=current_user.get("organization_id", "default"),
            user_id=current_user.get("id", ""),
            session_id=session_id,
            history=history,
        ))
    session_store.clear(session_id)


@router.post("/chat")
async def chat_assistant(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Chat with AI assistant. Routes to specialist agents: inventory, ops, finance, insights."""
    from services.assistant import chat
    from services import session_store
    from services.agents.memory_store import recall
    from services.agents.memory_extract import extract_and_save

    session_id = data.session_id or str(uuid.uuid4())
    org_id = current_user.get("organization_id", "default")
    user_id = current_user.get("id", "")
    history = session_store.get_or_create(session_id)

    if SESSION_COST_CAP > 0 and session_store.get_cost(session_id) >= SESSION_COST_CAP:
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

    # Inject memory context at the start of fresh sessions only
    if not history:
        memory_ctx = await recall(org_id=org_id, user_id=user_id)
        if memory_ctx:
            history = [
                {"role": "user", "content": memory_ctx},
                {"role": "assistant", "content": "Context noted from previous sessions."},
            ]

    ctx = {
        "org_id": org_id,
        "user_id": user_id,
        "user_name": current_user.get("name", ""),
    }
    result = await chat(
        (data.message or "").strip(),
        history=history,
        ctx=ctx,
        mode=data.mode,
        agent_type=data.agent_type,
    )

    new_history = result.pop("history", [])
    turn_cost = result.get("usage", {}).get("cost_usd", 0.0)
    session_store.update(session_id, new_history, cost_usd=turn_cost)

    # Background memory extraction every 4 turns (8 messages = 4 user+assistant pairs)
    if new_history and len(new_history) % 8 == 0:
        asyncio.create_task(extract_and_save(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            history=new_history,
        ))

    result["session_id"] = session_id
    result["usage"] = {**result.get("usage", {}), "session_cost_usd": session_store.get_cost(session_id)}
    return result
