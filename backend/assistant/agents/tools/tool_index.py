"""Tool index — semantic search over tool descriptors for retrieval.

When OPENAI_API_KEY is set, uses embeddings. Otherwise falls back to BM25.
Used to limit the unified agent to a subset of tools per request.
"""

from __future__ import annotations

import logging
import re

import numpy as np

from assistant.agents.tools.descriptors import get_unified_tool_descriptors
from shared.infrastructure.config import EMBEDDING_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)
DELEGATION_TOOLS = frozenset({"analyze_procurement", "analyze_trends", "assess_business_health"})
DEFAULT_TOP_K = 15

_tool_index: ToolIndex | None = None


def _tokenize(text: str) -> list[str]:
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
        logger.warning("Tool index embedding batch failed: %s", e)
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
        logger.warning("Tool index query embedding failed: %s", e)
        return None


class ToolIndex:
    """Semantic search over tool descriptors."""

    def __init__(self) -> None:
        self._names: list[str] = []
        self._texts: list[str] = []
        self._embeddings: np.ndarray | None = None
        self._bm25 = None

    async def rebuild(self) -> None:
        """Rebuild index from unified tool descriptors."""
        descriptors = get_unified_tool_descriptors()
        self._names = list(descriptors.keys())
        self._texts = [
            f"{d.name} {d.description} {' '.join(d.use_cases)}" for d in descriptors.values()
        ]
        if not self._texts:
            self._embeddings = None
            self._bm25 = None
            return

        if OPENAI_API_KEY:
            self._embeddings = await _embed_batch(self._texts, OPENAI_API_KEY)
            self._bm25 = None
            if self._embeddings is None:
                self._build_bm25()
        else:
            self._embeddings = None
            self._build_bm25()

    def _build_bm25(self) -> None:
        try:
            from rank_bm25 import BM25Okapi

            corpus = [_tokenize(t) for t in self._texts]
            self._bm25 = BM25Okapi(corpus)
        except ImportError:
            logger.warning("rank_bm25 not installed; tool retrieval will fall back to no filtering")
            self._bm25 = None

    async def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[str]:
        """Return tool names most relevant to query. Always includes delegation tools."""
        if not self._names:
            return []

        seen = set(DELEGATION_TOOLS)
        result: list[str] = []

        if self._embeddings is not None and OPENAI_API_KEY:
            qvec = await _embed_query(query, OPENAI_API_KEY)
            if qvec is not None:
                scores = np.dot(self._embeddings, qvec)
                idx = np.argsort(-scores)[: top_k + len(DELEGATION_TOOLS)]
                for i in idx:
                    name = self._names[i]
                    if name not in seen:
                        seen.add(name)
                        result.append(name)
                        if len(result) >= top_k:
                            break

        if self._bm25 is not None and len(result) < top_k:
            tok_q = _tokenize(query)
            try:
                scores = self._bm25.get_scores(tok_q)
                idx = np.argsort(-scores)[: top_k + len(DELEGATION_TOOLS)]
                for i in idx:
                    name = self._names[i]
                    if name not in seen:
                        seen.add(name)
                        result.append(name)
                        if len(result) >= top_k:
                            break
            except (ImportError, AttributeError):
                pass

        for d in DELEGATION_TOOLS:
            if d in self._names and d not in seen:
                result.append(d)
        return result[: top_k + len(DELEGATION_TOOLS)]


def get_tool_index() -> ToolIndex:
    """Return singleton tool index."""
    global _tool_index
    if _tool_index is None:
        _tool_index = ToolIndex()
    return _tool_index


async def retrieve_tools_for_query(query: str, top_k: int = DEFAULT_TOP_K) -> list[str] | None:
    """Return top-K tool names for query, or None to use all tools (fallback)."""
    index = get_tool_index()
    if not index._names:
        await index.rebuild()
    if not index._names:
        return None
    tools = await index.search(query, top_k=top_k)
    return tools if tools else None
