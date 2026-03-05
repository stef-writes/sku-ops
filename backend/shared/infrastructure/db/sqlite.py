"""SQLite backend using aiosqlite — wraps the existing single-connection pattern."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Sequence

import aiosqlite

from shared.infrastructure.db.protocol import Connection, DictRow


# ── Cursor wrapper ────────────────────────────────────────────────────────────

class SqliteCursor:
    __slots__ = ("_cursor",)

    def __init__(self, cursor: aiosqlite.Cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    async def fetchone(self) -> DictRow | None:
        row = await self._cursor.fetchone()
        return DictRow(dict(row)) if row is not None else None

    async def fetchall(self) -> list[DictRow]:
        rows = await self._cursor.fetchall()
        return [DictRow(dict(r)) for r in rows]


# ── Connection wrapper ────────────────────────────────────────────────────────

class SqliteConnection:
    """Thin wrapper around aiosqlite.Connection that satisfies the protocol."""
    __slots__ = ("_conn",)

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def execute(self, sql: str, params: tuple | list = ()) -> SqliteCursor:
        cursor = await self._conn.execute(sql, params)
        return SqliteCursor(cursor)

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        await self._conn.executemany(sql, params_list)

    async def executescript(self, sql: str) -> None:
        """SQLite-only helper for multi-statement DDL (used by migrations)."""
        await self._conn.executescript(sql)

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()


# ── Backend lifecycle ─────────────────────────────────────────────────────────

class SqliteBackend:
    dialect = "sqlite"

    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None

    async def connect(self, url: str) -> None:
        db_path = url.replace("sqlite:///", "").lstrip("/") if "://" in url else url
        if db_path == ":memory:":
            resolved = ":memory:"
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            resolved = str(p.resolve())

        self._conn = await aiosqlite.connect(resolved)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    def connection(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call connect() at startup.")
        return SqliteConnection(self._conn)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Connection]:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call connect() at startup.")
        wrapper = SqliteConnection(self._conn)
        await self._conn.execute("BEGIN")
        try:
            yield wrapper
            await wrapper.commit()
        except Exception:
            await wrapper.rollback()
            raise

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
