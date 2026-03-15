"""OAuth state persistence for Xero connect flow.

Owned by finance — the OAuth flow is for the Xero integration,
not a general auth concern.
"""

from datetime import UTC, datetime

from shared.infrastructure.database import get_connection, get_org_id


async def save_oauth_state(state: str) -> None:
    org_id = get_org_id()
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        """INSERT INTO oauth_states (state, org_id, created_at) VALUES ($1, $2, $3)
           ON CONFLICT(state) DO UPDATE SET org_id = $4, created_at = $5""",
        (state, org_id, now, org_id, now),
    )
    await conn.commit()


async def pop_oauth_state(state: str) -> str | None:
    conn = get_connection()
    cursor = await conn.execute("SELECT org_id FROM oauth_states WHERE state = $1", (state,))
    row = await cursor.fetchone()
    if not row:
        return None
    await conn.execute("DELETE FROM oauth_states WHERE state = $1", (state,))
    await conn.commit()
    return row[0]
