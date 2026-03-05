"""Schema runner — bootstraps the database from context schemas.

Architecture:
  Each bounded context owns its current table definitions in
  {context}/infrastructure/schema.py (TABLES, INDEXES).

  full_schema.py aggregates all context schemas in dependency order.

  On startup the runner checks whether the database has been initialized.
  If not, it creates every table and index from full_schema.py in one shot.

  There is no migration chain.  Schema changes are made directly in the
  context schema files and applied by re-creating the database.
"""
import logging

logger = logging.getLogger(__name__)


async def _table_exists(conn, table: str, *, dialect: str = "sqlite") -> bool:
    if dialect == "sqlite":
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
    else:
        cursor = await conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?", (table,)
        )
    return (await cursor.fetchone()) is not None


async def _bootstrap_full_schema(conn) -> None:
    """Create the full schema on a fresh database (any dialect)."""
    from full_schema import FULL_SCHEMA
    for stmt in FULL_SCHEMA:
        await conn.execute(stmt)
    await conn.commit()


async def run_migrations(backend) -> None:
    """Ensure the database schema exists.

    Fresh databases are bootstrapped from the context schemas (the single
    source of truth).  Already-initialized databases are left as-is.
    """
    dialect = backend.dialect
    conn = backend.connection()

    if not await _table_exists(conn, "users", dialect=dialect):
        logger.info("Fresh %s database — bootstrapping from context schemas", dialect)
        await _bootstrap_full_schema(conn)
        logger.info("Schema bootstrapped")
        return

    logger.debug("Database already initialized — skipping bootstrap")
