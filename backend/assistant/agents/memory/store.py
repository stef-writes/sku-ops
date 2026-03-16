"""Persistent cross-session memory for chat agents.

Artifacts are typed facts extracted from completed conversations.
They are recalled at the start of fresh sessions so agents have context
about recurring contractors, products, and user preferences.

Recall uses hybrid scoring (semantic similarity + recency + type boost)
when pgvector is available, falling back to date-ordered retrieval.
"""

import asyncio
import json
import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from shared.infrastructure.database import get_connection, get_org_id

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = 90

# Type boost weights for hybrid recall scoring.
_TYPE_BOOST: dict[str, float] = {
    "user_preference": 0.10,
    "decision": 0.08,
    "entity_fact": 0.04,
    "insight": 0.04,
    "session_summary": 0.0,
}


async def save(user_id: str, session_id: str, artifacts: list[dict]) -> None:
    """Persist a list of extracted artifacts to the DB.

    Also embeds each artifact and upserts to the embeddings table for
    semantic recall (fire-and-forget, non-blocking).
    """
    if not artifacts:
        return
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(days=_DEFAULT_TTL_DAYS)).isoformat()
    rows: list[tuple[Any, ...]] = []
    artifact_ids: list[str] = []
    artifact_contents: list[str] = []

    for a in artifacts:
        if not isinstance(a, dict) or not a.get("content"):
            continue
        aid = str(uuid.uuid4())
        content = (a.get("content") or "")[:1000]
        rows.append(
            (
                aid,
                org_id,
                user_id,
                session_id,
                (a.get("type") or "entity_fact")[:32],
                (a.get("subject") or "general")[:128],
                content,
                json.dumps(a.get("tags") or []),
                now,
                expires_at,
            )
        )
        artifact_ids.append(aid)
        # Embed the subject + content together for richer semantic matching
        subject = (a.get("subject") or "general")[:128]
        artifact_contents.append(f"{subject}: {content}")

    if not rows:
        return
    await conn.executemany(
        """INSERT INTO memory_artifacts
               (id, org_id, user_id, session_id, type, subject, content, tags, created_at, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
        rows,
    )
    await conn.commit()
    logger.info("Memory: saved %d artifacts for user=%s", len(rows), user_id)

    # Embed + persist vectors in background (non-blocking)
    asyncio.create_task(_embed_artifacts(org_id, artifact_ids, artifact_contents))


async def _embed_artifacts(org_id: str, artifact_ids: list[str], contents: list[str]) -> None:
    """Background task: embed memory artifacts and persist to pgvector."""
    try:
        from assistant.infrastructure.embedding_store import (
            embed_texts,
            is_pgvector_available,
            upsert_batch,
        )

        if not await is_pgvector_available():
            return
        vecs = await embed_texts(contents)
        if vecs is None:
            return
        items = [
            (aid, content, vec)
            for aid, content, vec in zip(artifact_ids, contents, vecs, strict=False)
        ]
        written = await upsert_batch(org_id, "memory", items)
        if written:
            logger.debug("Memory embeddings: wrote %d vectors", written)
    except Exception as e:
        logger.warning("Memory embedding failed (non-critical): %s", e)


async def recall(
    user_id: str,
    query: str | None = None,
    limit: int = 10,
) -> str:
    """Return a formatted context string of relevant artifacts for session injection.

    When *query* is provided and pgvector is available, uses hybrid scoring:
      0.6 * semantic_similarity + 0.3 * recency_decay + 0.1 * type_boost

    Falls back to date-ordered retrieval (original behavior) otherwise.
    Returns empty string if no artifacts exist.
    """
    conn = get_connection()
    org_id = get_org_id()
    now_str = datetime.now(UTC).isoformat()
    now_ts = datetime.now(UTC)

    # Try semantic recall first
    if query:
        rows = await _semantic_recall(org_id, user_id, query, now_str, now_ts, limit)
        if rows:
            return _format_rows(rows)

    # Fallback: date-ordered
    cur = await conn.execute(
        """SELECT type, subject, content, created_at
           FROM memory_artifacts
           WHERE org_id = $1 AND user_id = $2
             AND (expires_at IS NULL OR expires_at > $3)
           ORDER BY created_at DESC
           LIMIT $4""",
        (org_id, user_id, now_str, limit),
    )
    rows = await cur.fetchall()
    if not rows:
        return ""
    return _format_rows(rows)


async def _semantic_recall(
    org_id: str,
    user_id: str,
    query: str,
    now_str: str,
    now_ts: datetime,
    limit: int,
) -> list[dict] | None:
    """Attempt pgvector-based semantic recall with hybrid scoring.

    Returns None if pgvector or embeddings unavailable, triggering fallback.
    """
    try:
        from assistant.infrastructure.embedding_store import (
            embed_query,
            is_pgvector_available,
        )

        if not await is_pgvector_available():
            return None

        qvec = await embed_query(query)
        if qvec is None:
            return None

        from assistant.infrastructure.embedding_store import _vec_to_pgvector

        vec_str = _vec_to_pgvector(qvec)
        conn = get_connection()

        # Join memory_artifacts with embeddings for hybrid scoring
        cur = await conn.execute(
            """SELECT m.type, m.subject, m.content, m.created_at,
                      1 - (e.embedding <=> $1::vector) AS similarity
               FROM memory_artifacts m
               JOIN embeddings e ON e.entity_id = m.id AND e.entity_type = 'memory'
               WHERE m.org_id = $2 AND m.user_id = $3
                 AND (m.expires_at IS NULL OR m.expires_at > $4)
               ORDER BY similarity DESC
               LIMIT $5""",
            (vec_str, org_id, user_id, now_str, limit * 3),
        )
        candidates = await cur.fetchall()
        if not candidates:
            return None

        # Apply hybrid scoring
        scored = []
        for r in candidates:
            sim = float(r["similarity"])
            # Recency decay: e^(-0.02 * days_old) — 1.0 today, ~0.55 at 30d, ~0.16 at 90d
            created = r["created_at"] or ""
            try:
                created_dt = datetime.fromisoformat(created)
                days_old = max(0, (now_ts - created_dt).total_seconds() / 86400)
            except (ValueError, TypeError):
                days_old = 30  # assume moderate age if unparseable
            recency = math.exp(-0.02 * days_old)
            type_boost = _TYPE_BOOST.get(r["type"], 0.0)
            hybrid_score = 0.6 * sim + 0.3 * recency + 0.1 * (type_boost / 0.1)

            scored.append((hybrid_score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    except Exception as e:
        logger.debug("Semantic recall unavailable, falling back: %s", e)
        return None


def _format_rows(rows: list) -> str:
    """Format artifact rows as a context string for agent injection."""
    lines = ["[Memory from previous sessions — background context only, not ground truth]"]
    for r in rows:
        date = (r["created_at"] or "")[:10]
        lines.append(f"- [{r['type']}] {r['subject']}: {r['content']} ({date})")
    return "\n".join(lines)
