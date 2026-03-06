"""Example migration — placeholder to verify the migration system works.

This migration does nothing. It exists to seed the schema_versions table
so the runner has at least one migration to track. Replace or delete this
file before your first real schema change; or leave it — it's harmless.

Real migrations look like:

    async def up(conn, dialect: str) -> None:
        await conn.execute("ALTER TABLE products ADD COLUMN weight REAL DEFAULT 0")
"""


async def up(conn, dialect: str) -> None:
    pass
