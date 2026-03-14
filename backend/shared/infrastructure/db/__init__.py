"""Database package — drop-in replacement for the old database.py module.

Public API:
    init_db()        — call once at startup
    get_connection() — returns a Connection (protocol)
    transaction()    — async context manager yielding a Connection
    close_db()       — call once at shutdown
    get_org_id()     — ambient org_id for current request / job
    get_user_id()    — ambient user_id for current request / job

The backend (SQLite vs PostgreSQL) is selected automatically from DATABASE_URL.

Unit of Work: a contextvar stores the ambient transactional connection.
get_connection() returns it when inside a transaction() block, so repos
that call get_connection() automatically participate in the ambient
transaction without explicit conn threading.

Request context: org_id_var / user_id_var are set by auth middleware and
read by get_org_id() / get_user_id().  Repos call these instead of
accepting organization_id parameters.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from shared.infrastructure.config import DATABASE_URL
from shared.infrastructure.logging_config import org_id_var, user_id_var
from shared.kernel.constants import DEFAULT_ORG_ID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from shared.infrastructure.db.protocol import Connection, DatabaseBackend

_state: dict[str, DatabaseBackend | None] = {"backend": None}

_tx_conn: ContextVar[Connection | None] = ContextVar("_tx_conn", default=None)


class _ManagedTxProxy:
    """Wraps a transactional connection to suppress commit/rollback calls.

    Repos that still call ``conn.commit()`` or ``conn.rollback()`` will
    silently no-op when running inside a ``transaction()`` block — the
    context manager owns the commit/rollback lifecycle.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: Connection):
        self._conn = conn

    async def execute(self, sql: str, params: tuple | list = ()):
        return await self._conn.execute(sql, params)

    async def executemany(self, sql: str, params_list: Sequence[tuple | list]) -> None:
        return await self._conn.executemany(sql, params_list)

    async def executescript(self, sql: str) -> None:
        if hasattr(self._conn, "executescript"):
            await self._conn.executescript(sql)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


def _make_backend(url: str) -> DatabaseBackend:
    if url.startswith(("postgresql://", "postgres://")):
        from shared.infrastructure.db.postgres import PostgresBackend

        return PostgresBackend()
    from shared.infrastructure.db.sqlite import SqliteBackend

    return SqliteBackend()


async def init_db() -> None:
    """Open connection / pool and run pending migrations."""
    _state["backend"] = _make_backend(DATABASE_URL)
    await _state["backend"].connect(DATABASE_URL)

    from shared.infrastructure.migrations.runner import run_schema

    await run_schema(_state["backend"])


def get_org_id() -> str:
    """Return the ambient org_id for the current request or job context."""
    return org_id_var.get(DEFAULT_ORG_ID)


def get_user_id() -> str:
    """Return the ambient user_id for the current request or job context."""
    return user_id_var.get("")


def get_connection() -> Connection:
    """Return the ambient transactional connection if inside a transaction(),
    otherwise fall back to the default connection (pool proxy for PG, wrapper
    for SQLite)."""
    tx = _tx_conn.get()
    if tx is not None:
        return tx
    if _state["backend"] is None:
        raise RuntimeError("Database not initialized. Call init_db() at startup.")
    return _state["backend"].connection()


@asynccontextmanager
async def transaction() -> AsyncIterator[Connection]:
    """Async context manager — commits on success, rolls back on exception.

    Stores the transactional connection in a contextvar so that
    get_connection() returns it for the duration of the block.
    Nested calls reuse the existing ambient connection.
    """
    existing = _tx_conn.get()
    if existing is not None:
        yield existing
        return
    if _state["backend"] is None:
        raise RuntimeError("Database not initialized. Call init_db() at startup.")
    async with _state["backend"].transaction() as conn:
        proxy = _ManagedTxProxy(conn)
        token = _tx_conn.set(proxy)
        try:
            yield proxy
        finally:
            _tx_conn.reset(token)


async def drop_all_tables() -> None:
    """Drop all application tables in reverse FK dependency order.

    Connects to the database if not already initialized. After this call
    the database is empty — call init_db() to recreate the schema.

    Only for use in demo/reset flows (RESET_DB=true). Never call in production
    unless you explicitly intend to wipe all data.
    """
    if _state["backend"] is None:
        _state["backend"] = _make_backend(DATABASE_URL)
        await _state["backend"].connect(DATABASE_URL)
        opened_here = True
    else:
        opened_here = False

    conn = _state["backend"].connection()

    # Leaf tables first, root tables last (reverse FK dependency order)
    tables = [
        "assistant_messages",
        "vendor_items",
        "stock_transactions",
        "cycle_count_items",
        "cycle_counts",
        "withdrawal_items",
        "withdrawals",
        "return_items",
        "returns",
        "purchase_order_items",
        "purchase_orders",
        "invoice_items",
        "invoices",
        "documents",
        "job_items",
        "jobs",
        "skus",
        "sku_counters",
        "products",
        "vendors",
        "departments",
        "oauth_states",
        "refresh_tokens",
        "users",
        "organizations",
        "schema_versions",
    ]
    for table in tables:
        await conn.execute(f"DROP TABLE IF EXISTS {table}")
    await conn.commit()

    if opened_here:
        await _state["backend"].close()
        _state["backend"] = None


async def close_db() -> None:
    """Close connection / pool on shutdown."""
    if _state["backend"]:
        await _state["backend"].close()
        _state["backend"] = None
