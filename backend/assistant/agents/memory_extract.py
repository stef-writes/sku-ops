"""Background task: extract memory artifacts from completed chat sessions.

Called fire-and-forget via asyncio.create_task(). Never raises — failures are
logged as warnings and silently discarded so they never affect the user.
"""
import json
import logging

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
You extract key facts from chat conversations for long-term memory.

Given a conversation, return a JSON array (possibly []) of 0-5 facts worth remembering for future sessions.

Each item must be:
{"type": "entity_fact"|"session_summary"|"user_preference", "subject": "<domain>:<id> or 'general'", "content": "<1-2 sentence fact>", "tags": ["tag1"]}

Types:
- entity_fact: specific facts about contractors, products, or jobs (subject: "contractor:john-smith", "product:PLU-001")
- session_summary: what the user was investigating or working on (subject: "session")
- user_preference: how the user prefers data presented, what they care about (subject: "general")

Only extract genuinely useful, specific, non-obvious facts. Return [] if nothing notable.
Reply with the JSON array ONLY — no markdown, no other text."""


async def extract_and_save(
    org_id: str,
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
        import anthropic
        from shared.infrastructure.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
        if not ANTHROPIC_API_KEY:
            return

        # Format last 20 messages (10 pairs), truncating long turns
        turns = []
        for h in history[-20:]:
            role = (h.get("role") or "user").upper()
            content = (h.get("content") or "").strip()[:600]
            if content:
                turns.append(f"{role}: {content}")
        if len(turns) < 2:
            return

        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(turns)}],
        )
        raw = (response.content[0].text or "").strip()

        # Strip markdown code fences if model wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()

        artifacts = json.loads(raw)
        if isinstance(artifacts, list) and artifacts:
            from assistant.agents.memory_store import save
            await save(org_id, user_id, session_id, artifacts)

    except Exception as e:
        logger.warning(f"Memory extraction failed (non-critical): {e}")
