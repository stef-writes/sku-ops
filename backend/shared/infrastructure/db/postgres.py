"""PostgreSQL backend using asyncpg with connection pooling."""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import asyncpg

logger = logging.getLogger(__name__)

from shared.infrastructure.db.protocol import Connection, DictRow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

# ── Placeholder conversion ────────────────────────────────────────────────────

_Q_PLACEHOLDER = re.compile(r"\?")


def _convert_placeholders(sql: str) -> str:
    """Convert SQLite-style ``?`` placeholders to PostgreSQL ``$N``."""
    counter = 0

    def _replacer(_match: re.Match) -> str:
        nonlocal counter
        counter += 1
        return f"${counter}"

    return _Q_PLACEHOLDER.sub(_replacer, sql)


def _convert_sql(sql: str) -> str:
    """Full SQL dialect conversion: placeholders + syntax sugar."""
    had_or_ignore = "INSERT OR IGNORE" in sql
    converted = _convert_placeholders(sql)
    converted = converted.replace("INSERT OR IGNORE", "INSERT")
    converted = converted.replace("INSERT OR REPLACE", "INSERT")
    if had_or_ignore and "ON CONFLICT" not in converted:
        converted = re.sub(
            r"(VALUES\s*\([^)]+\))",
            r"\1 ON CONFLICT DO NOTHING",
            converted,
        )
    return converted


# ── Cursor wrapper ────────────────────────────────────────────────────────────

class PgCursor:
    __slots__ = ("_rows", "_status")

    def __init__(self, rows: list[asyncpg.Record], status: str = ""):
        self._rows = rows
        self._status = status

    @property
    def rowcount(self) -> int:
        parts = self._status.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
        return len(self._rows)

    async def fetchone(self) -> DictRow | None:
        if not self._rows:
            return None
        return DictRow(dict(self._rows[0]))

    async def fetchall(self) -> list[DictRow]:
        return [DictRow(dict(r)) for r in self._rows]


# ── Pool proxy (auto-acquire per statement) ───────────────────────────────────

class PgPoolProxy:
    """Returned by ``get_connection()`` — acquires per-execute, auto-commits."""
    __slots__ = ("_pool", "_acquire_timeout")

    def __init__(self, pool: asyncpg.Pool, acquire_timeout: float):
        self._pool = pool
        self._acquire_timeout = acquire_timeout

    async def execute(self, sql: str, params: tuple | list = ()) -> PgCursor:
        converted = _convert_sql(sql)
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            if converted.lstrip().upper().startswith("SELECT") or "RETURNING" in converted.upper():
                rows = await conn.fetch(converted, *params)
                return PgCursor(rows)
            status = await conn.execute(converted, *params)
            return PgCursor([], status or "")

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        converted = _convert_sql(sql)
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            await conn.executemany(converted, params_list)

    async def commit(self) -> None:
        pass  # autocommit outside transactions

    async def rollback(self) -> None:
        pass


# ── Transaction proxy (holds single connection) ──────────────────────────────

class PgTransactionProxy:
    """Used inside ``transaction()`` context — single connection, explicit commit.

    commit() and rollback() are intentional no-ops here; the context manager in
    PostgresBackend.transaction() owns the transaction lifecycle.  This avoids
    double-commit errors when application code calls ``await conn.commit()``
    inside the ``async with transaction()`` block (matching SQLite's lenient
    commit semantics).
    """
    __slots__ = ("_conn",)

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def execute(self, sql: str, params: tuple | list = ()) -> PgCursor:
        converted = _convert_sql(sql)
        if converted.lstrip().upper().startswith("SELECT") or "RETURNING" in converted.upper():
            rows = await self._conn.fetch(converted, *params)
            return PgCursor(rows)
        status = await self._conn.execute(converted, *params)
        return PgCursor([], status or "")

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        converted = _convert_sql(sql)
        await self._conn.executemany(converted, params_list)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


# ── Backend lifecycle ─────────────────────────────────────────────────────────

class PostgresBackend:
    dialect = "postgresql"

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._acquire_timeout: float = 30.0

    async def connect(self, url: str) -> None:
        min_size = int(os.environ.get("PG_POOL_MIN", "2"))
        max_size = int(os.environ.get("PG_POOL_MAX", "10"))
        command_timeout = int(os.environ.get("PG_COMMAND_TIMEOUT", "60"))
        self._acquire_timeout = float(os.environ.get("PG_ACQUIRE_TIMEOUT", "30"))

        if ":6543" in url:
            logger.warning(
                "DATABASE_URL uses port 6543 (Supabase pgbouncer). "
                "asyncpg uses prepared statements which are incompatible with "
                "pgbouncer in transaction mode. Use the direct connection on "
                "port 5432 instead."
            )

        self._pool = await asyncpg.create_pool(
            url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

    def connection(self) -> Connection:
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call connect() at startup.")
        return PgPoolProxy(self._pool, self._acquire_timeout)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Connection]:
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call connect() at startup.")
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                yield PgTransactionProxy(conn)
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
