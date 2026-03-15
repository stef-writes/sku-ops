"""PostgreSQL backend using asyncpg with connection pooling."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import asyncpg

logger = logging.getLogger(__name__)

from shared.infrastructure.db.protocol import Connection, DictRow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


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

    __slots__ = ("_acquire_timeout", "_pool")

    def __init__(self, pool: asyncpg.Pool, acquire_timeout: float):
        self._pool = pool
        self._acquire_timeout = acquire_timeout

    async def execute(self, sql: str, params: tuple | list = ()) -> PgCursor:
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            if sql.lstrip().upper().startswith("SELECT") or "RETURNING" in sql.upper():
                rows = await conn.fetch(sql, *params)
                return PgCursor(rows)
            status = await conn.execute(sql, *params)
            return PgCursor([], status or "")

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
            await conn.executemany(sql, params_list)

    async def commit(self) -> None:
        pass  # autocommit outside transactions

    async def rollback(self) -> None:
        pass


# ── Transaction proxy (holds single connection) ──────────────────────────────


class PgTransactionProxy:
    """Used inside ``transaction()`` context — single connection, explicit commit.

    commit() and rollback() are intentional no-ops here; the context manager in
    PostgresBackend.transaction() owns the transaction lifecycle.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def execute(self, sql: str, params: tuple | list = ()) -> PgCursor:
        if sql.lstrip().upper().startswith("SELECT") or "RETURNING" in sql.upper():
            rows = await self._conn.fetch(sql, *params)
            return PgCursor(rows)
        status = await self._conn.execute(sql, *params)
        return PgCursor([], status or "")

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        await self._conn.executemany(sql, params_list)

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
        from shared.infrastructure.config import (
            PG_ACQUIRE_TIMEOUT,
            PG_COMMAND_TIMEOUT,
            PG_POOL_MAX,
            PG_POOL_MIN,
        )

        min_size = PG_POOL_MIN
        max_size = PG_POOL_MAX
        command_timeout = PG_COMMAND_TIMEOUT
        self._acquire_timeout = PG_ACQUIRE_TIMEOUT

        if ":6543" in url:
            from shared.infrastructure.config import is_deployed

            msg = (
                "DATABASE_URL uses port 6543 (Supabase pgbouncer). "
                "asyncpg uses prepared statements which are incompatible with "
                "pgbouncer in transaction mode. Use the direct connection on "
                "port 5432 instead."
            )
            if is_deployed:
                raise RuntimeError(msg)
            logger.warning(msg)

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
