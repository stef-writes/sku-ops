"""Database protocol — interface contract for SQLite and PostgreSQL adapters."""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


class DictRow(dict):
    """Dict that also supports integer-index access (row[0], row[1]).

    aiosqlite.Row supported both ``row["col"]`` and ``row[0]``.
    This preserves backward compat for all existing repo code that uses
    either access pattern.
    """

    def __init__(self, mapping):
        super().__init__(mapping)
        self._keys = list(mapping.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


def to_dict_row(mapping) -> DictRow:
    """Convert any mapping (dict, asyncpg.Record, aiosqlite.Row) to DictRow."""
    return DictRow(dict(mapping))


@runtime_checkable
class Cursor(Protocol):
    """Minimal cursor returned by Connection.execute()."""

    @property
    def rowcount(self) -> int: ...

    async def fetchone(self) -> DictRow | None: ...

    async def fetchall(self) -> list[DictRow]: ...


@runtime_checkable
class Connection(Protocol):
    """Async database connection (single conn or pool proxy)."""

    async def execute(self, sql: str, params: tuple | list = ()) -> Cursor: ...

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class DatabaseBackend(Protocol):
    """Lifecycle manager for a database backend (SQLite or PostgreSQL)."""

    dialect: str  # "sqlite" or "postgresql"

    async def connect(self, url: str) -> None: ...

    def connection(self) -> Connection: ...

    def transaction(self) -> AbstractAsyncContextManager[Connection]: ...

    async def close(self) -> None: ...
