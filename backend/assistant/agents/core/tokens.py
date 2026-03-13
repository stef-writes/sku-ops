"""Token counting and budget management via tiktoken.

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


def compress_history(
    history: list[dict] | None,
    max_tokens: int = 8000,
) -> list[dict] | None:
    """Trim conversation history to fit within *max_tokens*.

    Keeps the most recent turns and drops oldest first.
    """
    if not history:
        return history
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
