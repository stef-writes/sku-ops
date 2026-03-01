"""Database connection and configuration - SQLite with aiosqlite."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/sku_ops.db")
# Extract path from sqlite:///path or use as-is if plain path
_db_path = DATABASE_URL.replace("sqlite:///", "").lstrip("/") if "://" in DATABASE_URL else DATABASE_URL

_conn: aiosqlite.Connection | None = None


def _get_db_path() -> str:
    path = Path(_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


async def init_db() -> None:
    """Create tables if not exist, enable WAL mode."""
    global _conn
    path = _get_db_path()
    _conn = await aiosqlite.connect(path)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA foreign_keys=ON")

    await _conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'warehouse_manager',
            company TEXT,
            billing_entity TEXT,
            phone TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS departments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            product_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vendors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact_name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            product_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            sku TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price REAL NOT NULL,
            cost REAL NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            min_stock INTEGER NOT NULL DEFAULT 5,
            department_id TEXT NOT NULL,
            department_name TEXT NOT NULL DEFAULT '',
            vendor_id TEXT,
            vendor_name TEXT NOT NULL DEFAULT '',
            original_sku TEXT,
            barcode TEXT,
            base_unit TEXT NOT NULL DEFAULT 'each',
            sell_uom TEXT NOT NULL DEFAULT 'each',
            pack_qty INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE INDEX IF NOT EXISTS idx_products_department ON products(department_id);
        CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
        CREATE INDEX IF NOT EXISTS idx_products_vendor ON products(vendor_id);
        CREATE INDEX IF NOT EXISTS idx_products_vendor_original_sku ON products(vendor_id, original_sku);

        CREATE TABLE IF NOT EXISTS withdrawals (
            id TEXT PRIMARY KEY,
            items TEXT NOT NULL,
            job_id TEXT NOT NULL,
            service_address TEXT NOT NULL,
            notes TEXT,
            subtotal REAL NOT NULL,
            tax REAL NOT NULL,
            total REAL NOT NULL,
            cost_total REAL NOT NULL,
            contractor_id TEXT NOT NULL,
            contractor_name TEXT NOT NULL DEFAULT '',
            contractor_company TEXT NOT NULL DEFAULT '',
            billing_entity TEXT NOT NULL DEFAULT '',
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            invoice_id TEXT,
            paid_at TEXT,
            processed_by_id TEXT NOT NULL,
            processed_by_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_withdrawals_contractor ON withdrawals(contractor_id);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_created ON withdrawals(created_at);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(payment_status);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_billing ON withdrawals(billing_entity);

        CREATE TABLE IF NOT EXISTS payment_transactions (
            id TEXT PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            withdrawal_id TEXT,
            user_id TEXT,
            contractor_id TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'usd',
            metadata TEXT,
            payment_status TEXT NOT NULL DEFAULT 'pending',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            paid_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sku_counters (
            department_code TEXT PRIMARY KEY,
            counter INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS stock_transactions (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            sku TEXT NOT NULL,
            product_name TEXT NOT NULL DEFAULT '',
            quantity_delta INTEGER NOT NULL,
            quantity_before INTEGER NOT NULL,
            quantity_after INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            reference_id TEXT,
            reference_type TEXT,
            reason TEXT,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stock_product ON stock_transactions(product_id);
        CREATE INDEX IF NOT EXISTS idx_stock_created ON stock_transactions(created_at);
        CREATE INDEX IF NOT EXISTS idx_stock_product_created ON stock_transactions(product_id, created_at);

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            invoice_number TEXT UNIQUE NOT NULL,
            billing_entity TEXT NOT NULL DEFAULT '',
            contact_name TEXT NOT NULL DEFAULT '',
            contact_email TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            subtotal REAL NOT NULL,
            tax REAL NOT NULL,
            total REAL NOT NULL,
            notes TEXT,
            xero_invoice_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_withdrawals (
            invoice_id TEXT NOT NULL,
            withdrawal_id TEXT NOT NULL,
            PRIMARY KEY (invoice_id, withdrawal_id),
            FOREIGN KEY (invoice_id) REFERENCES invoices(id),
            FOREIGN KEY (withdrawal_id) REFERENCES withdrawals(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_line_items (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            amount REAL NOT NULL,
            product_id TEXT,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
        CREATE INDEX IF NOT EXISTS idx_invoices_billing ON invoices(billing_entity);
        CREATE INDEX IF NOT EXISTS idx_invoice_line_items_invoice ON invoice_line_items(invoice_id);

        CREATE TABLE IF NOT EXISTS invoice_counters (
            key TEXT PRIMARY KEY,
            counter INTEGER NOT NULL DEFAULT 0
        );
    """)
    # Migration: add UOM columns to products if missing
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN base_unit TEXT NOT NULL DEFAULT 'each'")
        await _conn.commit()
    except Exception:
        pass
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN sell_uom TEXT NOT NULL DEFAULT 'each'")
        await _conn.commit()
    except Exception:
        pass
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN pack_qty INTEGER NOT NULL DEFAULT 1")
        await _conn.commit()
    except Exception:
        pass
    # Migration: enforce SKU uniqueness (drop non-unique index, create unique index)
    try:
        await _conn.execute("DROP INDEX IF EXISTS idx_products_sku")
        await _conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        await _conn.commit()
    except Exception:
        pass


def get_connection() -> aiosqlite.Connection:
    """Return the shared database connection. Must call init_db() first."""
    if _conn is None:
        raise RuntimeError("Database not initialized. Call init_db() at startup.")
    return _conn


@asynccontextmanager
async def transaction():
    """
    Async context manager for database transactions.
    Commits on success, rolls back on exception.
    Yields the connection for use by repos (pass conn to avoid their commit).
    """
    conn = get_connection()
    await conn.execute("BEGIN")
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise


async def close_db() -> None:
    """Close the database connection on shutdown."""
    global _conn
    if _conn:
        await _conn.close()
        _conn = None
