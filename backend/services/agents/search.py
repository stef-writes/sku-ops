"""
BM25 product search index. Builds in-memory from the products table on startup.
Provides semantic/conceptual search beyond exact SKU/name matching.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Registry: org_id → ProductSearchIndex
_indexes: dict[str, "ProductSearchIndex"] = {}


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, remove short tokens."""
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1]


class ProductSearchIndex:
    def __init__(self):
        self._bm25 = None
        self._products: list[dict] = []

    async def rebuild(self, org_id: str = "default") -> None:
        """Fetch all products and build BM25 index."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed — semantic search unavailable. Run: pip install rank-bm25")
            return

        from repositories import product_repo
        products = await product_repo.list_products(limit=10000, org_id=org_id)
        if not products:
            self._products = []
            self._bm25 = None
            return

        corpus = []
        for p in products:
            tokens = _tokenize(f"{p.get('name', '')} {p.get('description', '')} {p.get('department_name', '')} {p.get('vendor_name', '')}")
            corpus.append(tokens if tokens else ["_"])

        self._bm25 = BM25Okapi(corpus)
        self._products = products
        logger.info(f"BM25 index built: {len(products)} products (org={org_id})")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return top-k products matching the query."""
        if not self._bm25 or not self._products:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # Pair scores with products, filter zero-score, sort descending
        ranked = sorted(
            ((score, p) for score, p in zip(scores, self._products) if score > 0),
            key=lambda x: x[0],
            reverse=True,
        )
        return [p for _, p in ranked[:limit]]

    def is_ready(self) -> bool:
        return self._bm25 is not None


async def get_index(org_id: str = "default") -> ProductSearchIndex:
    """Return (building if needed) the BM25 index for the given org."""
    if org_id not in _indexes:
        index = ProductSearchIndex()
        _indexes[org_id] = index
        await index.rebuild(org_id)
    return _indexes[org_id]


async def refresh_index(org_id: str = "default") -> None:
    """Rebuild the index for an org (call after product create/update/delete)."""
    index = _indexes.get(org_id)
    if index is None:
        index = ProductSearchIndex()
        _indexes[org_id] = index
    await index.rebuild(org_id)
