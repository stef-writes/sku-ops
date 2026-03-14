"""Schema bootstrap — creates all tables and indexes on a fresh database.

Each bounded context owns its current table definitions in
{context}/infrastructure/schema.py (TABLES, INDEXES).

full_schema.py aggregates all context schemas in dependency order.

On startup the runner:
  1. Runs every CREATE TABLE IF NOT EXISTS from full_schema.py (idempotent).
  2. Runs every CREATE INDEX IF NOT EXISTS.
  3. Applies shared reference data (SEED statements).

This is intentionally simple: no migration tracking, no versioned changes.
For a schema change, update the relevant schema.py, drop the database,
and re-run. Use a proper migration tool (Alembic) if/when live migrations
are required.
"""

import logging

logger = logging.getLogger(__name__)


async def run_schema(backend) -> None:
    """Bootstrap the database schema.

    Safe to call on an already-initialised database — all statements use
    CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
    """
    conn = backend.connection()
    from shared.infrastructure.full_schema import ALL_INDEXES, ALL_TABLES
    from shared.infrastructure.schema import SEED as _shared_seed

    for stmt in ALL_TABLES:
        await conn.execute(stmt)
    await conn.commit()

    for stmt in ALL_INDEXES + _shared_seed:
        await conn.execute(stmt)
    await conn.commit()

    logger.debug("Schema bootstrap complete")
