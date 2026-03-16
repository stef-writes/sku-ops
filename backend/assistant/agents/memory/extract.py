"""Background task: extract memory artifacts from completed chat sessions.

Called fire-and-forget via asyncio.create_task(). Never raises — failures are
logged as warnings and silently discarded so they never affect the user.

Uses the active LLM provider (OpenRouter or Anthropic) when available.
"""

import asyncio
import json
import logging

from assistant.agents.core.model_registry import get_model_name
from assistant.agents.memory.store import save
from assistant.infrastructure.llm import get_provider
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = load_prompt(__file__, "prompt.md")


async def extract_and_save(
    user_id: str,
    session_id: str,
    history: list[dict],
) -> None:
    """Extract facts from conversation history and persist as memory artifacts.

    Designed to run as a background asyncio task — swallows all exceptions.
    """
    if not history or len(history) < 4:
        return
    try:
        try:
            provider = get_provider()
        except RuntimeError:
            return
        if not provider.available or provider.provider_name == "stub":
            return

        turns = []
        for h in history[-20:]:
            role = (h.get("role") or "user").upper()
            content = (h.get("content") or "").strip()[:600]
            if content:
                turns.append(f"{role}: {content}")
        if len(turns) < 2:
            return

        prompt = "\n\n".join(turns)
        model_id = get_model_name("infra:synthesis")
        raw = await asyncio.to_thread(provider.generate_text, prompt, _EXTRACT_SYSTEM, model_id)
        if not raw or not raw.strip():
            return

        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()

        artifacts = json.loads(raw)
        if isinstance(artifacts, list) and artifacts:
            await save(user_id, session_id, artifacts)

    except (json.JSONDecodeError, ValueError, TypeError, RuntimeError, OSError) as e:
        logger.warning("Memory extraction failed (non-critical): %s", e)
