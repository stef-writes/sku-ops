"""Chat assistant entrypoint. Dispatches directly to the appropriate specialist agent."""
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL
from assistant.agents.deps import AgentDeps

LLM_NOT_CONFIGURED_MSG = (
    "Chat assistant requires an Anthropic API key. Add ANTHROPIC_API_KEY to backend/.env. "
    f"Get a key at {LLM_SETUP_URL}"
)

_AGENT_MODULES = {
    "inventory": "assistant.agents.inventory",
    "ops":       "assistant.agents.ops",
    "finance":   "assistant.agents.finance",
    "insights":  "assistant.agents.insights",
    "general":   "assistant.agents.general",
    "dashboard": "assistant.agents.general",  # alias for general (dashboard assistant)
}


async def chat(
    user_message: str,
    history: list[dict] | None,
    ctx: dict | None = None,
    mode: str = "fast",
    agent_type: str = "general",
) -> dict:
    """
    Dispatch user message directly to the appropriate specialist agent.
    history: prior turns from session_store (owned by caller)
    agent_type: "inventory" | "ops" | "finance" | "insights" | "general"
    ctx: {"org_id": str, "user_id": str, "user_name": str}
    """
    if not ANTHROPIC_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": [], "history": [], "agent": None}

    ctx = ctx or {}
    deps = AgentDeps(
        org_id=ctx.get("org_id", "default"),
        user_id=ctx.get("user_id", ""),
        user_name=ctx.get("user_name", ""),
    )

    import importlib
    module_path = _AGENT_MODULES.get(agent_type, _AGENT_MODULES["general"])
    agent_module = importlib.import_module(module_path)
    return await agent_module.run(user_message, history=history, deps=deps, mode=mode)
