"""Token counting, budget management, and context compression.

Uses cl100k_base encoding as an approximation for both Anthropic and
OpenRouter models.  Not exact, but close enough for budget decisions.
"""

import json
import logging

import tiktoken

logger = logging.getLogger(__name__)

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return approximate token count for a string."""
    if not text:
        return 0
    return len(_enc.encode(text))


# ── Tool result budgeting ─────────────────────────────────────────────────────
# Fields to drop first when trimming (low information density).
# sell_uom is NOT here — the system prompt requires UOM in every answer.
_LOW_VALUE_FIELDS = frozenset(
    (
        "_note",
        "method",
        "original_sku",
        "barcode",
    )
)

# JSON keys that typically contain list items
_LIST_KEYS = (
    "products",
    "forecast",
    "suggestions",
    "slow_movers",
    "withdrawals",
    "balances",
    "pending_requests",
    "departments",
    "vendors",
    "items",
)


def budget_tool_result(raw_json: str, max_tokens: int = 2000) -> str:
    """Truncate a tool's JSON output if it exceeds *max_tokens*.

    Strategy (applied in order until under budget):
    1. Drop low-value fields from each item in lists
    2. Trim the list to fewer items (keep first N)
    3. Hard character-level truncation as last resort
    """
    tokens = count_tokens(raw_json)
    if tokens <= max_tokens:
        return raw_json

    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return raw_json[: max_tokens * 4]  # ~4 chars per token fallback

    # Phase 1: drop low-value fields from list items
    for key in _LIST_KEYS:
        items = data.get(key)
        if isinstance(items, list):
            data[key] = [
                {k: v for k, v in item.items() if k not in _LOW_VALUE_FIELDS}
                if isinstance(item, dict)
                else item
                for item in items
            ]

    trimmed = json.dumps(data, separators=(",", ":"))
    if count_tokens(trimmed) <= max_tokens:
        return trimmed

    # Phase 2: reduce list length
    for key in _LIST_KEYS:
        items = data.get(key)
        if isinstance(items, list) and len(items) > 3:
            original_count = len(items)
            while (
                len(items) > 3
                and count_tokens(json.dumps(data, separators=(",", ":"))) > max_tokens
            ):
                items.pop()
            data[key] = items
            data[f"_{key}_truncated"] = f"{len(items)}/{original_count} shown"

    trimmed = json.dumps(data, separators=(",", ":"))
    if count_tokens(trimmed) <= max_tokens:
        return trimmed

    # Phase 3: hard truncation
    chars = max_tokens * 3
    return trimmed[:chars] + '..."}'


def estimate_turn_tokens(
    system_prompt: str,
    history: list[dict] | None,
    user_message: str,
) -> dict[str, int]:
    """Pre-flight estimate of input tokens for an agent turn."""
    sys_tokens = count_tokens(system_prompt)
    msg_tokens = count_tokens(user_message)
    hist_tokens = 0
    if history:
        hist_tokens = sum(count_tokens(h.get("content", "")) for h in history)
    overhead = 50  # framing tokens (role markers, separators)
    return {
        "system": sys_tokens,
        "history": hist_tokens,
        "user_message": msg_tokens,
        "overhead": overhead,
        "total_estimate": sys_tokens + hist_tokens + msg_tokens + overhead,
    }


# ── History compression ───────────────────────────────────────────────────────


# Synchronous fallback — drop oldest turns, keep most recent.
def _compress_truncate(
    history: list[dict],
    max_tokens: int = 8000,
) -> list[dict]:
    """Trim conversation history by dropping oldest turns first."""
    if len(history) <= 4:
        return history

    total = sum(count_tokens(h.get("content", "")) for h in history)
    if total <= max_tokens:
        return history

    # Always keep the last 2 turns
    kept = list(history[-2:])
    budget_remaining = max_tokens - sum(count_tokens(h.get("content", "")) for h in kept)

    # Add older turns from most-recent backward until budget exhausted
    for h in reversed(history[:-2]):
        t = count_tokens(h.get("content", ""))
        if budget_remaining - t < 0:
            break
        kept.insert(0, h)
        budget_remaining -= t

    return kept


def compress_history(
    history: list[dict] | None,
    max_tokens: int = 8000,
) -> list[dict] | None:
    """Synchronous compression — truncation only. Use for non-async callers."""
    if not history:
        return history
    return _compress_truncate(history, max_tokens)


async def compress_history_async(
    history: list[dict] | None,
    max_tokens: int = 8000,
) -> list[dict] | None:
    """Async compression with progressive summarization.

    Before dropping old turns, summarizes them with a cheap LLM call so
    the reasoning chain is preserved.  Falls back to truncation if the
    LLM is unavailable or fails.

    Strategy:
        Tier 1 — Last 3 turns (6 messages) kept verbatim
        Tier 2 — Older turns summarized into ~300 tokens
        Tier 3 — If summary + recent still too large, truncate recent
    """
    if not history:
        return history
    if len(history) <= 6:
        return history

    total = sum(count_tokens(h.get("content", "")) for h in history)
    if total <= max_tokens:
        return history

    # Split into recent (keep) and older (summarize)
    recent = history[-6:]  # last 3 turns
    older = history[:-6]

    if not older:
        return _compress_truncate(history, max_tokens)

    # Attempt progressive summarization
    summary = await _summarize_turns(older)
    if summary:
        result = [
            {"role": "system", "content": f"[Prior conversation summary]: {summary}"},
            *recent,
        ]
        result_tokens = sum(count_tokens(h.get("content", "")) for h in result)
        if result_tokens <= max_tokens:
            return result
        # Summary + recent still too long — trim the recent portion
        return _compress_truncate(result, max_tokens)

    # LLM unavailable — fall back to truncation
    return _compress_truncate(history, max_tokens)


async def _summarize_turns(turns: list[dict], max_summary_tokens: int = 300) -> str | None:
    """Summarize conversation turns using a cheap model.

    Returns None if LLM is unavailable. Never raises.
    """
    try:
        from assistant.infrastructure.llm import get_provider

        provider = get_provider()
        if not provider.available or provider.provider_name == "stub":
            return None

        from assistant.agents.core.model_registry import get_model_name

        model_id = get_model_name("infra:synthesis")

        # Build a compact representation of the turns
        lines = []
        for t in turns:
            role = (t.get("role") or "user").upper()
            content = (t.get("content") or "").strip()[:400]
            if content:
                lines.append(f"{role}: {content}")
        if not lines:
            return None

        import asyncio

        text = "\n".join(lines)
        result = await asyncio.to_thread(
            provider.generate_text,
            text,
            "Summarize this conversation concisely. Preserve: entity names, "
            "numbers, decisions made, questions still open, and any user "
            "preferences expressed. Max 3-4 sentences.",
            model_id,
        )
        return result.strip() if result else None

    except Exception as e:
        logger.debug("Turn summarization failed (non-critical): %s", e)
        return None
