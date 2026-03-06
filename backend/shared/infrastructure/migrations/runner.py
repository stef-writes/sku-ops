"""Schema runner — bootstraps the database and applies versioned migrations.

Architecture:
  Each bounded context owns its current table definitions in
  {context}/infrastructure/schema.py (TABLES, INDEXES).

  full_schema.py aggregates all context schemas in dependency order.

  On startup the runner:
    1. Runs every CREATE TABLE/INDEX IF NOT EXISTS from full_schema.py
       (safe on existing DBs — idempotent).
    2. Creates a schema_versions table to track applied migrations.
    3. Applies any pending versioned migrations from the versions/ package.

  Versioned migrations handle ALTER TABLE, data transforms, and any
  change that CREATE TABLE IF NOT EXISTS cannot express. Each migration
  is a numbered Python module with an async up(conn, dialect) function.

  The schema.py files remain the source of truth for fresh databases.
  Migrations are only needed for evolving an existing database.
"""
import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

_SCHEMA_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_SCHEMA_VERSIONS_DDL_PG = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


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


async def _ensure_versions_table(conn, dialect: str) -> None:
    ddl = _SCHEMA_VERSIONS_DDL_PG if dialect != "sqlite" else _SCHEMA_VERSIONS_DDL
    await conn.execute(ddl)
    await conn.commit()


async def _get_applied_versions(conn) -> set[int]:
    cursor = await conn.execute("SELECT version FROM schema_versions ORDER BY version")
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


def _discover_migrations() -> list[tuple[int, str, object]]:
    """Discover migration modules in the versions/ package.

    Each module must be named NNN_description.py (e.g., 001_add_foo_column.py)
    and must define an async function: up(conn, dialect: str) -> None
    """
    import shared.infrastructure.migrations.versions as versions_pkg

    migrations = []
    for importer, modname, ispkg in pkgutil.iter_modules(versions_pkg.__path__):
        if ispkg or modname.startswith("_"):
            continue
        parts = modname.split("_", 1)
        if not parts[0].isdigit():
            logger.warning("Skipping migration %s — name must start with a number", modname)
            continue
        version = int(parts[0])
        mod = importlib.import_module(f"shared.infrastructure.migrations.versions.{modname}")
        if not hasattr(mod, "up"):
            logger.warning("Skipping migration %s — no up() function", modname)
            continue
        migrations.append((version, modname, mod))

    migrations.sort(key=lambda m: m[0])
    return migrations


async def _apply_pending_migrations(conn, dialect: str) -> int:
    """Apply any migrations not yet recorded in schema_versions. Returns count applied."""
    applied = await _get_applied_versions(conn)
    migrations = _discover_migrations()
    count = 0

    for version, name, mod in migrations:
        if version in applied:
            continue
        logger.info("Applying migration %03d: %s", version, name)
        try:
            await mod.up(conn, dialect)
            await conn.execute(
                "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
                (version, name),
            )
            await conn.commit()
            count += 1
            logger.info("Migration %03d applied", version)
        except Exception:
            logger.exception("Migration %03d failed — aborting", version)
            raise

    return count


async def run_migrations(backend) -> None:
    """Ensure the database schema is up to date.

    1. Run all CREATE TABLE/INDEX IF NOT EXISTS (idempotent).
    2. Create schema_versions table if missing.
    3. Apply pending versioned migrations.
    """
    conn = backend.connection()
    from full_schema import FULL_SCHEMA

    is_fresh = not await _table_exists(conn, "users", dialect=backend.dialect)
    if is_fresh:
        logger.info("Fresh database — bootstrapping schema")
    else:
        logger.debug("Existing database — applying any missing tables/indexes")

    for stmt in FULL_SCHEMA:
        await conn.execute(stmt)
    await conn.commit()

    if is_fresh:
        logger.info("Schema bootstrapped")

    await _ensure_versions_table(conn, backend.dialect)
    applied = await _apply_pending_migrations(conn, backend.dialect)
    if applied:
        logger.info("Applied %d migration(s)", applied)
