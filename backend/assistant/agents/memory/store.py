"""Persistent cross-session memory for chat agents.

Artifacts are typed facts extracted from completed conversations.
They are recalled at the start of fresh sessions so agents have context
about recurring contractors, products, and user preferences.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from shared.infrastructure.database import get_connection, get_org_id

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = 90


async def save(user_id: str, session_id: str, artifacts: list[dict]) -> None:
    """Persist a list of extracted artifacts to the DB."""
    if not artifacts:
        return
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(days=_DEFAULT_TTL_DAYS)).isoformat()
    rows: list[tuple[Any, ...]] = [
        (
            str(uuid.uuid4()),
            org_id,
            user_id,
            session_id,
            (a.get("type") or "entity_fact")[:32],
            (a.get("subject") or "general")[:128],
            (a.get("content") or "")[:1000],
            json.dumps(a.get("tags") or []),
            now,
            expires_at,
        )
        for a in artifacts
        if isinstance(a, dict) and a.get("content")
    ]
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


async def recall(user_id: str, limit: int = 15) -> str:
    """Return a formatted context string of recent artifacts for session injection.

    Returns empty string if no artifacts exist (avoids any overhead on first session).
    """
    conn = get_connection()
    org_id = get_org_id()
    now = datetime.now(UTC).isoformat()
    cur = await conn.execute(
        """SELECT type, subject, content, created_at
           FROM memory_artifacts
           WHERE org_id = $1 AND user_id = $2
             AND (expires_at IS NULL OR expires_at > $3)
           ORDER BY created_at DESC
           LIMIT $4""",
        (org_id, user_id, now, limit),
    )
    rows = await cur.fetchall()
    if not rows:
        return ""
    lines = ["[Memory from previous sessions — background context only, not ground truth]"]
    for r in rows:
        date = (r["created_at"] or "")[:10]
        lines.append(f"- [{r['type']}] {r['subject']}: {r['content']} ({date})")
    return "\n".join(lines)
