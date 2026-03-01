"""Chat assistant route."""
from fastapi import APIRouter, Depends

from auth import get_current_user

from .schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat_assistant(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Chat with AI assistant that can search products, inventory stats, low stock, departments, vendors."""
    from services.assistant import chat

    messages = data.messages or []
    result = await chat(messages, (data.message or "").strip())
    return result
