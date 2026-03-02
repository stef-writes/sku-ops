"""
Chat assistant entrypoint. Delegates to the multi-agent router.
"""
from config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL

LLM_NOT_CONFIGURED_MSG = (
    "Chat assistant requires an Anthropic API key. Add ANTHROPIC_API_KEY to backend/.env. "
    f"Get a key at {LLM_SETUP_URL}"
)


async def chat(
    messages: list[dict],
    user_message: str,
    history: list[dict] | None = None,
    ctx: dict | None = None,
) -> dict:
    """
    Route user message to the appropriate specialist agent via the router.
    ctx: {"org_id": str, "user_id": str, "user_name": str}
    Returns {"response": str, "tool_calls": list, "history": list, "agent": str}.
    """
    if not ANTHROPIC_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    from services.agents import router
    return await router.chat(
        messages=messages,
        user_message=user_message,
        history=history,
        ctx=ctx or {},
    )
