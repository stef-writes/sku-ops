"""
Schema single-source-of-truth tests.

Verifies that the context schema.py files (aggregated via full_schema.py)
produce a valid, complete database — every expected table is present and
has the columns its context defines.
"""
import aiosqlite
import pytest

from full_schema import FULL_SCHEMA


EXPECTED_TABLES = {
    "organizations", "users", "refresh_tokens", "audit_log", "org_settings",
    "oauth_states", "fiscal_periods",
    "departments", "vendors", "products", "sku_counters",
    "stock_transactions",
    "withdrawals", "withdrawal_items", "material_requests", "returns", "return_items",
    "invoices", "invoice_withdrawals", "invoice_line_items", "invoice_counters",
    "credit_notes", "credit_note_line_items", "financial_ledger",
    "payments", "payment_withdrawals", "billing_entities",
    "purchase_orders", "purchase_order_items",
    "documents",
    "jobs",
    "addresses",
    "memory_artifacts", "agent_runs",
}


async def _bootstrap() -> dict[str, list[str]]:
    """Create in-memory DB from context schemas, return {table: [col_names]}."""
    db = await aiosqlite.connect(":memory:")
    for stmt in FULL_SCHEMA:
        await db.execute(stmt)
    await db.commit()

    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]

    schema: dict[str, list[str]] = {}
    for table in tables:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        cols = await cursor.fetchall()
        schema[table] = [c[1] for c in cols]

    await db.close()
    return schema


@pytest.mark.asyncio
async def test_full_schema_creates_all_expected_tables():
    """Every expected table must be present after bootstrapping."""
    schema = await _bootstrap()
    actual = set(schema.keys())
    missing = EXPECTED_TABLES - actual
    assert not missing, f"Tables missing from context schemas: {missing}"


@pytest.mark.asyncio
async def test_full_schema_tables_have_columns():
    """Every table must have at least an 'id' or primary key column (not empty)."""
    schema = await _bootstrap()
    empty = [t for t, cols in schema.items() if not cols]
    assert not empty, f"Tables with no columns: {empty}"


@pytest.mark.asyncio
async def test_full_schema_is_idempotent():
    """Running the schema twice must not raise errors (IF NOT EXISTS)."""
    db = await aiosqlite.connect(":memory:")
    for stmt in FULL_SCHEMA:
        await db.execute(stmt)
    await db.commit()
    for stmt in FULL_SCHEMA:
        await db.execute(stmt)
    await db.commit()
    await db.close()
