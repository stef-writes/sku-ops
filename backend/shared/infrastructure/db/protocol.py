"""Database protocol — interface contract for the PostgreSQL adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractAsyncContextManager


class DictRow(dict):
    """Dict that also supports integer-index access (row[0], row[1])."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self._keys = list(mapping.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


def to_dict_row(mapping) -> DictRow:
    """Convert any mapping (dict, asyncpg.Record) to DictRow."""
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
    """Async database connection (pool proxy or transaction proxy)."""

    async def execute(self, sql: str, params: tuple | list = ()) -> Cursor: ...

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class DatabaseBackend(Protocol):
    """Lifecycle manager for the PostgreSQL backend."""

    dialect: str

    async def connect(self, url: str) -> None: ...

    def connection(self) -> Connection: ...

    def transaction(self) -> AbstractAsyncContextManager[Connection]: ...

    async def close(self) -> None: ...
