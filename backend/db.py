"""Database connection and configuration - SQLite with aiosqlite."""
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from config import DATABASE_URL
# Extract path from sqlite:///path or use as-is if plain path
_db_path = DATABASE_URL.replace("sqlite:///", "").lstrip("/") if "://" in DATABASE_URL else DATABASE_URL

_conn: aiosqlite.Connection | None = None


def _get_db_path() -> str:
    if _db_path == ":memory:":
        return ":memory:"
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

        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS material_requests (
            id TEXT PRIMARY KEY,
            contractor_id TEXT NOT NULL,
            contractor_name TEXT NOT NULL DEFAULT '',
            items TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            withdrawal_id TEXT,
            job_id TEXT,
            service_address TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            processed_by_id TEXT,
            organization_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_material_requests_contractor ON material_requests(contractor_id);
        CREATE INDEX IF NOT EXISTS idx_material_requests_status ON material_requests(status);
        CREATE INDEX IF NOT EXISTS idx_material_requests_org ON material_requests(organization_id);

        CREATE TABLE IF NOT EXISTS purchase_orders (
            id TEXT PRIMARY KEY,
            vendor_id TEXT,
            vendor_name TEXT NOT NULL DEFAULT '',
            document_date TEXT,
            total REAL,
            status TEXT NOT NULL DEFAULT 'ordered',
            notes TEXT,
            created_by_id TEXT NOT NULL DEFAULT '',
            created_by_name TEXT NOT NULL DEFAULT '',
            received_at TEXT,
            received_by_id TEXT,
            received_by_name TEXT,
            created_at TEXT NOT NULL,
            organization_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_po_org_status ON purchase_orders(organization_id, status);
        CREATE INDEX IF NOT EXISTS idx_po_created ON purchase_orders(created_at);

        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id TEXT PRIMARY KEY,
            po_id TEXT NOT NULL,
            name TEXT NOT NULL,
            original_sku TEXT,
            ordered_qty INTEGER NOT NULL DEFAULT 1,
            delivered_qty INTEGER,
            price REAL NOT NULL DEFAULT 0,
            cost REAL NOT NULL DEFAULT 0,
            base_unit TEXT NOT NULL DEFAULT 'each',
            sell_uom TEXT NOT NULL DEFAULT 'each',
            pack_qty INTEGER NOT NULL DEFAULT 1,
            suggested_department TEXT NOT NULL DEFAULT 'HDW',
            status TEXT NOT NULL DEFAULT 'ordered',
            product_id TEXT,
            organization_id TEXT,
            FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
        );

        CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(po_id);
        CREATE INDEX IF NOT EXISTS idx_po_items_status ON purchase_order_items(status);
    """)
    # Migration: add vendor_barcode column for manufacturer UPC/EAN on product packaging
    try:
        await _conn.execute("ALTER TABLE products ADD COLUMN vendor_barcode TEXT")
        await _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_vendor_barcode ON products(vendor_barcode) WHERE vendor_barcode IS NOT NULL AND TRIM(vendor_barcode) != ''"
        )
        await _conn.commit()
    except Exception:
        pass

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
    # Migration: barcode uniqueness - dedupe first, then create index
    try:
        cursor = await _conn.execute("""
            SELECT barcode FROM products
            WHERE barcode IS NOT NULL AND TRIM(barcode) != ''
            GROUP BY barcode HAVING COUNT(*) > 1
        """)
        dupes = [row[0] for row in await cursor.fetchall()]
        for barcode in dupes:
            cursor = await _conn.execute(
                "SELECT id, sku FROM products WHERE barcode = ? ORDER BY created_at",
                (barcode,),
            )
            rows = await cursor.fetchall()
            for i, row in enumerate(rows):
                if i > 0:
                    pid, psku = row["id"], row["sku"]
                    await _conn.execute(
                        "UPDATE products SET barcode = ? WHERE id = ?",
                        (psku, pid),
                    )
        await _conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode) WHERE barcode IS NOT NULL AND TRIM(barcode) != ''"
        )
        await _conn.commit()
    except Exception:
        pass

    # Migration: multi-tenant - add organization_id to all tables
    _org_tables = [
        "users", "departments", "vendors", "products", "withdrawals",
        "invoices", "payment_transactions", "stock_transactions"
    ]
    for t in _org_tables:
        try:
            await _conn.execute(f"ALTER TABLE {t} ADD COLUMN organization_id TEXT")
            await _conn.commit()
        except Exception:
            pass
    # Create default org and backfill
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await _conn.execute(
            "INSERT OR IGNORE INTO organizations (id, name, slug, created_at) VALUES ('default', 'Default', 'default', ?)",
            (now,),
        )
        for t in _org_tables:
            await _conn.execute(f"UPDATE {t} SET organization_id = 'default' WHERE organization_id IS NULL")
        await _conn.commit()
    except Exception:
        pass
    # Add org indexes
    for t in _org_tables:
        try:
            await _conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_org ON {t}(organization_id)")
            await _conn.commit()
        except Exception:
            pass

    # Migration: departments - drop global code UNIQUE, add UNIQUE(organization_id, code)
    try:
        await _conn.execute("PRAGMA foreign_keys=OFF")
        await _conn.execute("DROP TABLE IF EXISTS departments_new")
        await _conn.execute("""
            CREATE TABLE departments_new (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                product_count INTEGER NOT NULL DEFAULT 0,
                organization_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, code)
            )
        """)
        await _conn.execute("""
            INSERT INTO departments_new (id, name, code, description, product_count, organization_id, created_at)
            SELECT id, name, code, description, product_count, COALESCE(organization_id, 'default'), created_at
            FROM departments
        """)
        await _conn.execute("DROP TABLE departments")
        await _conn.execute("ALTER TABLE departments_new RENAME TO departments")
        await _conn.execute("CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(organization_id)")
        await _conn.execute("PRAGMA foreign_keys=ON")
        await _conn.commit()
    except Exception:
        await _conn.execute("PRAGMA foreign_keys=ON")
        pass

    # Migration: rename 'pending' PO/item status to 'ordered' (3-state lifecycle)
    try:
        await _conn.execute(
            "UPDATE purchase_order_items SET status = 'ordered' WHERE status = 'pending'"
        )
        await _conn.execute(
            "UPDATE purchase_orders SET status = 'ordered' WHERE status = 'pending'"
        )
        await _conn.commit()
    except Exception:
        pass

    # Migration: add cost to invoice_line_items for COGS tracking
    try:
        await _conn.execute(
            "ALTER TABLE invoice_line_items ADD COLUMN cost REAL NOT NULL DEFAULT 0"
        )
        await _conn.commit()
    except Exception:
        pass  # column already exists

    # Migration: per-org settings (Xero config, account codes)
    try:
        await _conn.execute("""
            CREATE TABLE IF NOT EXISTS org_settings (
                organization_id TEXT PRIMARY KEY,
                xero_client_id TEXT,
                xero_client_secret TEXT,
                xero_tenant_id TEXT,
                xero_access_token TEXT,
                xero_refresh_token TEXT,
                xero_token_expiry TEXT,
                xero_sales_account_code TEXT NOT NULL DEFAULT '200',
                xero_cogs_account_code TEXT NOT NULL DEFAULT '500',
                xero_inventory_account_code TEXT NOT NULL DEFAULT '630',
                updated_at TEXT
            )
        """)
        await _conn.commit()
    except Exception:
        pass

    # Migration: additional Xero fields in org_settings
    for col_def in [
        "xero_ap_account_code TEXT NOT NULL DEFAULT '800'",
        "xero_tracking_category_id TEXT",
        "xero_tax_type TEXT NOT NULL DEFAULT ''",
    ]:
        try:
            await _conn.execute(f"ALTER TABLE org_settings ADD COLUMN {col_def}")
            await _conn.commit()
        except Exception:
            pass  # column already exists

    # Migration: job_id on invoice_line_items for per-line Xero tracking
    try:
        await _conn.execute("ALTER TABLE invoice_line_items ADD COLUMN job_id TEXT")
        await _conn.commit()
    except Exception:
        pass

    # Migration: cross-session memory artifacts
    try:
        await _conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_artifacts (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'entity_fact',
                subject TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                expires_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_artifacts(org_id, user_id, expires_at);
            CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_artifacts(session_id);
        """)
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
