"""Versioned schema migrations.

Each file is named NNN_description.py and must define:

    async def up(conn, dialect: str) -> None:
        ...

Migrations run in numeric order on startup, after the IF NOT EXISTS
bootstrap. They are recorded in the schema_versions table and never re-run.

Guidelines:
  - Keep migrations idempotent where possible (guard with IF NOT EXISTS, etc.)
  - Never modify or delete a migration that has been applied to any database.
  - Test both SQLite and PostgreSQL paths when dialect-specific SQL is needed.
"""
