"""Chat assistant route."""
from fastapi import APIRouter, Depends

from auth import get_current_user
from config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL

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


@router.post("/chat")
async def chat_assistant(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Chat with AI assistant. Routes to specialist agents: inventory, ops, finance, insights."""
    from services.assistant import chat

    ctx = {
        "org_id": current_user.get("organization_id", "default"),
        "user_id": current_user.get("id", ""),
        "user_name": current_user.get("name", ""),
    }
    messages = data.messages or []
    result = await chat(messages, (data.message or "").strip(), history=data.history, ctx=ctx)
    return result
