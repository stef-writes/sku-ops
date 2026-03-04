"""
Product search index. Uses OpenAI text-embedding-3-small for semantic search when
OPENAI_API_KEY is set; falls back to BM25 keyword search otherwise.
"""
import logging
import re

import numpy as np

from catalog.application.queries import list_products
from shared.infrastructure.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Registry: org_id → ProductSearchIndex
_indexes: dict[str, "ProductSearchIndex"] = {}


def _tokenize(text: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1]


def _product_text(p: dict) -> str:
    parts = [
        p.get("name") or "",
        p.get("description") or "",
        p.get("department_name") or "",
        p.get("vendor_name") or "",
        p.get("sku") or "",
    ]
    return " ".join(filter(None, parts))


class ProductSearchIndex:
    def __init__(self):
        self._products: list[dict] = []
        # Semantic (OpenAI embeddings)
        self._embeddings: np.ndarray | None = None   # shape (N, EMBEDDING_DIM)
        # Keyword fallback (BM25)
        self._bm25 = None

    async def rebuild(self, org_id: str = "default") -> None:
        products = await list_products(limit=10000, organization_id=org_id)
        if not products:
            self._products = []
            self._embeddings = None
            self._bm25 = None
            return

        self._products = products

        if OPENAI_API_KEY:
            await self._build_embeddings(products, OPENAI_API_KEY)
        else:
            self._build_bm25(products)

    async def _build_embeddings(self, products: list[dict], api_key: str) -> None:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            texts = [_product_text(p) for p in products]
            # Batch into chunks of 500 (API limit is 2048 inputs)
            all_vectors: list[list[float]] = []
            batch_size = 500
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
                all_vectors.extend(item.embedding for item in resp.data)
            mat = np.array(all_vectors, dtype=np.float32)
            # Normalize for cosine similarity via dot product
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            self._embeddings = mat / norms
            self._bm25 = None
            logger.info(f"Embedding index built: {len(products)} products (org={self._products[0].get('organization_id', 'unknown') if products else '?'})")
        except Exception as e:
            logger.warning(f"Embedding build failed, falling back to BM25: {e}")
            self._embeddings = None
            self._build_bm25(products)

    def _build_bm25(self, products: list[dict]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed — keyword search unavailable")
            return
        corpus = [_tokenize(_product_text(p)) or ["_"] for p in products]
        self._bm25 = BM25Okapi(corpus)
        logger.info(f"BM25 index built: {len(products)} products (fallback mode)")

    async def search_semantic(self, query: str, limit: int = 10, api_key: str = "") -> list[dict]:
        """Embed the query and return nearest products by cosine similarity."""
        if self._embeddings is None or not self._products:
            return self.search_bm25(query, limit)
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
            qvec = np.array(resp.data[0].embedding, dtype=np.float32)
            norm = np.linalg.norm(qvec)
            if norm > 0:
                qvec /= norm
            scores = self._embeddings @ qvec
            top_idx = np.argsort(scores)[::-1][:limit]
            return [self._products[i] for i in top_idx if scores[i] > 0.2]
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to BM25: {e}")
            return self.search_bm25(query, limit)

    def search_bm25(self, query: str, limit: int = 10) -> list[dict]:
        if not self._bm25 or not self._products:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            ((score, p) for score, p in zip(scores, self._products) if score > 0),
            key=lambda x: x[0],
            reverse=True,
        )
        return [p for _, p in ranked[:limit]]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Sync BM25 search — used as keyword fallback from tool wrappers that can't await."""
        return self.search_bm25(query, limit)

    def is_ready(self) -> bool:
        return bool(self._products)


async def get_index(org_id: str = "default") -> ProductSearchIndex:
    if org_id not in _indexes:
        index = ProductSearchIndex()
        _indexes[org_id] = index
        await index.rebuild(org_id)
    return _indexes[org_id]


async def refresh_index(org_id: str = "default") -> None:
    index = _indexes.get(org_id)
    if index is None:
        index = ProductSearchIndex()
        _indexes[org_id] = index
    await index.rebuild(org_id)
