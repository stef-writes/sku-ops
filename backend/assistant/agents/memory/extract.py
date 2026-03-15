"""Background task: extract memory artifacts from completed chat sessions.

Called fire-and-forget via asyncio.create_task(). Never raises — failures are
logged as warnings and silently discarded so they never affect the user.
"""

import json
import logging

import anthropic

import shared.infrastructure.config as _cfg
from assistant.agents.memory.store import save
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
        if not _cfg.ANTHROPIC_API_KEY:
            return

        turns = []
        for h in history[-20:]:
            role = (h.get("role") or "user").upper()
            content = (h.get("content") or "").strip()[:600]
            if content:
                turns.append(f"{role}: {content}")
        if len(turns) < 2:
            return

        client = anthropic.AsyncAnthropic(api_key=_cfg.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=_cfg.ANTHROPIC_MODEL,
            max_tokens=512,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(turns)}],
        )
        block = response.content[0]
        raw = (getattr(block, "text", "") or "").strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()

        artifacts = json.loads(raw)
        if isinstance(artifacts, list) and artifacts:
            await save(user_id, session_id, artifacts)

    except (json.JSONDecodeError, ValueError, TypeError, RuntimeError, OSError) as e:
        logger.warning("Memory extraction failed (non-critical): %s", e)
