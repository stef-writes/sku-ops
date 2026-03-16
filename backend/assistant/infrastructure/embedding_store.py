"""Persistent embedding store — pgvector-backed with in-memory fallback.

Consolidates all embedding operations (previously duplicated in search.py,
query_router.py, tool_index.py) into a single module.  Embeddings are
persisted in the ``embeddings`` table when pgvector is available, eliminating
the costly startup rebuild.  Falls back to transient NumPy matrices otherwise.

Public API:
    embed_texts(texts)       — batch embed, return (N, 1536) ndarray
    embed_query(query)       — single query embed, return (1536,) ndarray
    upsert(org, type, id, content, vec) — persist to DB with content-hash diffing
    search(query_vec, org, types, limit)  — ANN search via pgvector
    is_pgvector_available()  — whether persistent storage is usable
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

import numpy as np

from shared.infrastructure.config import EMBEDDING_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536

# ── Module state ──────────────────────────────────────────────────────────────
_pgvector_ok: bool | None = None  # None = not yet checked


async def is_pgvector_available() -> bool:
    """Check (and cache) whether the embeddings table exists and is usable."""
    global _pgvector_ok
    if _pgvector_ok is not None:
        return _pgvector_ok
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        cur = await conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'embeddings' LIMIT 1"
        )
        row = await cur.fetchone()
        _pgvector_ok = row is not None
    except Exception:
        _pgvector_ok = False
    logger.info("pgvector available: %s", _pgvector_ok)
    return _pgvector_ok


def reset_pgvector_check() -> None:
    """Reset the cached pgvector check (useful for tests)."""
    global _pgvector_ok
    _pgvector_ok = None


# ── Embedding generation (OpenAI) ────────────────────────────────────────────


def _normalize(mat: np.ndarray) -> np.ndarray:
    """L2-normalize rows so dot product == cosine similarity."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return mat / norms


async def embed_texts(
    texts: list[str],
    api_key: str | None = None,
    batch_size: int = 500,
) -> np.ndarray | None:
    """Embed a list of texts via OpenAI. Returns (N, 1536) normalized ndarray."""
    key = api_key or OPENAI_API_KEY
    if not key or not texts:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key)
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            all_vectors.extend(item.embedding for item in resp.data)
        mat = np.array(all_vectors, dtype=np.float32)
        return _normalize(mat)
    except (ValueError, RuntimeError, OSError, TypeError) as e:
        logger.warning("embed_texts failed: %s", e)
        return None


async def embed_query(
    query: str,
    api_key: str | None = None,
) -> np.ndarray | None:
    """Embed a single query string. Returns (1536,) normalized vector."""
    key = api_key or OPENAI_API_KEY
    if not key or not query:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key)
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
        qvec = np.array(resp.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(qvec)
        if norm > 0:
            qvec /= norm
        return qvec
    except (ValueError, RuntimeError, OSError, TypeError) as e:
        logger.warning("embed_query failed: %s", e)
        return None


# ── Content hashing ───────────────────────────────────────────────────────────


def content_hash(text: str) -> str:
    """SHA-256 hash of text content. Used to skip re-embedding unchanged content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── pgvector persistence ─────────────────────────────────────────────────────


def _vec_to_pgvector(vec: np.ndarray) -> str:
    """Format a numpy vector as a pgvector literal string."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def upsert(
    org_id: str,
    entity_type: str,
    entity_id: str,
    content: str,
    embedding: np.ndarray,
) -> bool:
    """Persist an embedding. Returns True if written, False if unchanged or unavailable."""
    if not await is_pgvector_available():
        return False
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        chash = content_hash(content)

        # Check if content is unchanged
        cur = await conn.execute(
            "SELECT content_hash FROM embeddings "
            "WHERE org_id = $1 AND entity_type = $2 AND entity_id = $3",
            (org_id, entity_type, entity_id),
        )
        existing = await cur.fetchone()
        if existing and existing["content_hash"] == chash:
            return False

        now = datetime.now(UTC).isoformat()
        vec_str = _vec_to_pgvector(embedding)
        row_id = f"{entity_type}:{entity_id}"

        if existing:
            await conn.execute(
                "UPDATE embeddings SET content = $1, content_hash = $2, "
                "embedding = $3::vector, updated_at = $4 "
                "WHERE org_id = $5 AND entity_type = $6 AND entity_id = $7",
                (content, chash, vec_str, now, org_id, entity_type, entity_id),
            )
        else:
            await conn.execute(
                "INSERT INTO embeddings (id, org_id, entity_type, entity_id, "
                "content, content_hash, embedding, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8)",
                (row_id, org_id, entity_type, entity_id, content, chash, vec_str, now),
            )
        await conn.commit()
        return True
    except Exception as e:
        logger.warning("embedding upsert failed: %s", e)
        return False


async def upsert_batch(
    org_id: str,
    entity_type: str,
    items: list[tuple[str, str, np.ndarray]],
) -> int:
    """Batch upsert embeddings. items = [(entity_id, content, vector), ...].

    Returns count of rows written (skips unchanged content).
    """
    if not await is_pgvector_available() or not items:
        return 0
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        now = datetime.now(UTC).isoformat()
        written = 0

        # Fetch existing hashes for diff
        ids = [i[0] for i in items]
        # Build a lookup of existing content hashes
        existing_hashes: dict[str, str] = {}
        # Query in batches to avoid huge IN clauses
        for batch_start in range(0, len(ids), 200):
            batch_ids = ids[batch_start : batch_start + 200]
            placeholders = ", ".join(f"${i + 3}" for i in range(len(batch_ids)))
            cur = await conn.execute(
                f"SELECT entity_id, content_hash FROM embeddings "
                f"WHERE org_id = $1 AND entity_type = $2 AND entity_id IN ({placeholders})",
                (org_id, entity_type, *batch_ids),
            )
            for row in await cur.fetchall():
                existing_hashes[row["entity_id"]] = row["content_hash"]

        rows_to_upsert: list[tuple] = []
        for entity_id, content_text, vec in items:
            chash = content_hash(content_text)
            if existing_hashes.get(entity_id) == chash:
                continue
            row_id = f"{entity_type}:{entity_id}"
            vec_str = _vec_to_pgvector(vec)
            rows_to_upsert.append(
                (row_id, org_id, entity_type, entity_id, content_text, chash, vec_str, now)
            )

        if rows_to_upsert:
            await conn.executemany(
                "INSERT INTO embeddings (id, org_id, entity_type, entity_id, "
                "content, content_hash, embedding, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8) "
                "ON CONFLICT (org_id, entity_type, entity_id) DO UPDATE SET "
                "content = EXCLUDED.content, content_hash = EXCLUDED.content_hash, "
                "embedding = EXCLUDED.embedding, updated_at = EXCLUDED.updated_at",
                rows_to_upsert,
            )
            await conn.commit()
            written = len(rows_to_upsert)

        return written
    except Exception as e:
        logger.warning("embedding batch upsert failed: %s", e)
        return 0


async def search(
    query_embedding: np.ndarray,
    org_id: str,
    entity_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Semantic search via pgvector cosine distance.

    Returns list of {entity_type, entity_id, content, similarity}.
    Falls back to empty list if pgvector unavailable.
    """
    if not await is_pgvector_available():
        return []
    try:
        from shared.infrastructure.database import get_connection

        conn = get_connection()
        vec_str = _vec_to_pgvector(query_embedding)

        if entity_types:
            placeholders = ", ".join(f"${i + 3}" for i in range(len(entity_types)))
            cur = await conn.execute(
                f"SELECT entity_type, entity_id, content, "
                f"1 - (embedding <=> $1::vector) AS similarity "
                f"FROM embeddings "
                f"WHERE org_id = $2 AND entity_type IN ({placeholders}) "
                f"ORDER BY embedding <=> $1::vector "
                f"LIMIT ${len(entity_types) + 3}",
                (vec_str, org_id, *entity_types, limit),
            )
        else:
            cur = await conn.execute(
                "SELECT entity_type, entity_id, content, "
                "1 - (embedding <=> $1::vector) AS similarity "
                "FROM embeddings "
                "WHERE org_id = $2 "
                "ORDER BY embedding <=> $1::vector "
                "LIMIT $3",
                (vec_str, org_id, limit),
            )
        rows = await cur.fetchall()
        return [
            {
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "content": r["content"],
                "similarity": float(r["similarity"]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("embedding search failed: %s", e)
        return []
