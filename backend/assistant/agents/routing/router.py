"""Simplified intent classifier — heuristic keyword scoring only.

Two public functions:
  is_trivial(message) -> bool   — greetings, help, thanks
  classify_domain(message) -> str — "inventory" | "ops" | "finance"
"""
import logging

logger = logging.getLogger(__name__)


# ── Trivial detection ─────────────────────────────────────────────────────────

_TRIVIAL_SIGNALS = frozenset((
    "hi", "hello", "hey", "thanks", "thank you", "help", "ok", "okay",
    "sure", "yes", "no", "bye", "goodbye", "good morning", "good afternoon",
))


def is_trivial(message: str) -> bool:
    """Return True for greetings, thanks, and other zero-data messages."""
    m = message.lower().strip()
    return len(m) < 20 and any(w in m for w in _TRIVIAL_SIGNALS)


# ── Domain classification ─────────────────────────────────────────────────────

_INVENTORY_WORDS = (
    "stock", "reorder", "sku", "barcode", "product", "low stock", "out of stock",
    "department", "vendor", "inventory", "slow mover", "dead stock",
    "top sell", "best sell", "top product", "forecast", "stockout",
    "velocity", "trend", "analytics",
)

_OPS_WORDS = (
    "withdrawal", "material request", "contractor", "job", "service address",
    "pulled", "who took", "pending request", "taken",
)

_FINANCE_WORDS = (
    "revenue", "invoice", "payment", "p&l", "profit", "margin", "outstanding",
    "owes", "xero", "balance", "sales", "gross", "unpaid", "billing",
)


def classify_domain(message: str) -> str:
    """Classify a message into one of the 3 specialist domains.

    Returns "inventory" (default), "ops", or "finance".
    """
    m = message.lower().strip()

    scores = {
        "inventory": sum(1 for w in _INVENTORY_WORDS if w in m),
        "ops": sum(1 for w in _OPS_WORDS if w in m),
        "finance": sum(1 for w in _FINANCE_WORDS if w in m),
    }

    hits = {k: v for k, v in scores.items() if v > 0}
    if not hits:
        return "inventory"

    return max(hits, key=lambda k: hits[k])
