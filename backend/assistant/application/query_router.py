"""Query router — route messages to unified agent or specialist.

Uses embedding-based routing: example queries per agent, pick nearest.
Falls back to unified when embeddings unavailable or confidence low.
"""

from __future__ import annotations

import logging

import numpy as np

from shared.infrastructure.config import EMBEDDING_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

AgentRoute = str  # "unified" | "procurement" | "trend" | "health"

_ROUTE_EXAMPLES: dict[str, list[str]] = {
    "procurement": [
        "Which vendor for SKU X?",
        "Reorder plan for low stock",
        "Optimize purchasing",
        "Vendor performance",
        "What should we order?",
        "Which vendor supplies this?",
        "Procurement plan",
        "Reorder with vendor context",
    ],
    "trend": [
        "Compare to last month",
        "Trend in revenue",
        "Anomaly in sales",
        "Growth rate",
        "What changed compared to last week?",
        "Revenue over time",
        "Period over period",
        "Time series",
    ],
    "health": [
        "Business health",
        "What needs attention",
        "Quarterly review",
        "Holistic assessment",
        "How's the business?",
        "Overall business health",
        "Comprehensive review",
    ],
    "unified": [
        "Product lookup",
        "Finance summary",
        "Invoice status",
        "Search for product",
        "Low stock list",
        "Revenue and P&L",
        "Mixed question",
    ],
}

_agent_texts: list[str] = []
_agent_labels: list[str] = []
_embeddings: np.ndarray | None = None
_bm25 = None


def _tokenize(text: str) -> list[str]:
    import re

    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1]


async def _embed_batch(texts: list[str], api_key: str) -> np.ndarray | None:
    if not texts:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        all_vectors: list[list[float]] = []
        batch_size = 256
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            all_vectors.extend(item.embedding for item in resp.data)
        mat = np.array(all_vectors, dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return mat / norms
    except (ValueError, RuntimeError, OSError, TypeError) as e:
        logger.warning("Router embedding batch failed: %s", e)
        return None


async def _embed_query(query: str, api_key: str) -> np.ndarray | None:
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
        qvec = np.array(resp.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(qvec)
        if norm > 0:
            qvec /= norm
        return qvec
    except (ValueError, RuntimeError, OSError, TypeError) as e:
        logger.warning("Router query embedding failed: %s", e)
        return None


def _build_router_index() -> None:
    """Build static index from route examples."""
    global _agent_texts, _agent_labels, _bm25
    _agent_texts = []
    _agent_labels = []
    for agent, examples in _ROUTE_EXAMPLES.items():
        for ex in examples:
            _agent_texts.append(ex)
            _agent_labels.append(agent)
    if not _agent_texts:
        return
    try:
        from rank_bm25 import BM25Okapi

        corpus = [_tokenize(t) for t in _agent_texts]
        _bm25 = BM25Okapi(corpus)
    except ImportError:
        _bm25 = None


async def _ensure_router_index() -> None:
    """Build embeddings if we have API key and haven't yet."""
    global _embeddings
    if _agent_texts and _embeddings is not None:
        return
    if _agent_texts and OPENAI_API_KEY:
        _embeddings = await _embed_batch(_agent_texts, OPENAI_API_KEY)


_GENERIC_GREETINGS = frozenset({"hello", "hi", "hey", "howdy", "yo"})


async def route_query(
    user_message: str,
    history: list[dict] | None = None,
) -> AgentRoute:
    """Route user message to unified or specialist agent. Returns agent label."""
    query = (user_message or "").strip()
    if not query:
        return "unified"
    if len(query) < 12 or query.lower() in _GENERIC_GREETINGS:
        return "unified"

    if not _agent_texts:
        _build_router_index()
    if not _agent_texts:
        return "unified"

    await _ensure_router_index()
    if len(query) < 15 or query.lower() in ("hello", "hi", "hey", "hello!", "hi!"):
        return "unified"

    if _embeddings is not None and OPENAI_API_KEY:
        qvec = await _embed_query(query, OPENAI_API_KEY)
        if qvec is not None:
            scores = np.dot(_embeddings, qvec)
            best_idx = int(np.argmax(scores))
            route = _agent_labels[best_idx]
            logger.debug("Router: embedded route=%s for query=%s", route, query[:50])
            return route

    if _bm25 is not None:
        tok_q = _tokenize(query)
        scores = _bm25.get_scores(tok_q)
        best_idx = int(np.argmax(scores))
        route = _agent_labels[best_idx]
        logger.debug("Router: BM25 route=%s for query=%s", route, query[:50])
        return route

    return "unified"
