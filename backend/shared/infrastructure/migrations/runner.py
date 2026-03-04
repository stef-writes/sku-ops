"""Sequential migration runner with schema_migrations tracking.

Each migration is an async function. The runner:
1. Creates schema_migrations table on first run.
2. Detects existing fully-migrated databases and fast-forwards history.
3. Applies pending migrations in order, recording each on success.
"""
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cursor = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return any(row[1] == column for row in rows)


async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return await cursor.fetchone() is not None


async def _index_exists(conn: aiosqlite.Connection, index: str) -> bool:
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index,)
    )
    return await cursor.fetchone() is not None


# ── migrations ────────────────────────────────────────────────────────────────

async def _001_initial_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
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


async def _002_vendor_barcode(conn: aiosqlite.Connection) -> None:
    if not await _column_exists(conn, "products", "vendor_barcode"):
        await conn.execute("ALTER TABLE products ADD COLUMN vendor_barcode TEXT")
    if not await _index_exists(conn, "idx_products_vendor_barcode"):
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_vendor_barcode ON products(vendor_barcode)"
            " WHERE vendor_barcode IS NOT NULL AND TRIM(vendor_barcode) != ''"
        )
    await conn.commit()


async def _003_uom_columns(conn: aiosqlite.Connection) -> None:
    for col, definition in [
        ("base_unit", "TEXT NOT NULL DEFAULT 'each'"),
        ("sell_uom", "TEXT NOT NULL DEFAULT 'each'"),
        ("pack_qty", "INTEGER NOT NULL DEFAULT 1"),
    ]:
        if not await _column_exists(conn, "products", col):
            await conn.execute(f"ALTER TABLE products ADD COLUMN {col} {definition}")
    await conn.commit()


async def _004_sku_uniqueness(conn: aiosqlite.Connection) -> None:
    await conn.execute("DROP INDEX IF EXISTS idx_products_sku")
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
    await conn.commit()


async def _005_barcode_uniqueness(conn: aiosqlite.Connection) -> None:
    # Deduplicate: for each duplicate barcode, set barcode = sku on all but the earliest row.
    cursor = await conn.execute("""
        SELECT barcode FROM products
        WHERE barcode IS NOT NULL AND TRIM(barcode) != ''
        GROUP BY barcode HAVING COUNT(*) > 1
    """)
    dupes = [row[0] for row in await cursor.fetchall()]
    for barcode in dupes:
        cursor = await conn.execute(
            "SELECT id, sku FROM products WHERE barcode = ? ORDER BY created_at",
            (barcode,),
        )
        rows = await cursor.fetchall()
        for i, row in enumerate(rows):
            if i > 0:
                await conn.execute(
                    "UPDATE products SET barcode = ? WHERE id = ?",
                    (row["sku"], row["id"]),
                )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)"
        " WHERE barcode IS NOT NULL AND TRIM(barcode) != ''"
    )
    await conn.commit()


async def _006_multi_tenant(conn: aiosqlite.Connection) -> None:
    org_tables = [
        "users", "departments", "vendors", "products", "withdrawals",
        "invoices", "payment_transactions", "stock_transactions",
    ]
    for table in org_tables:
        if not await _column_exists(conn, table, "organization_id"):
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN organization_id TEXT")
    await conn.commit()

    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "INSERT OR IGNORE INTO organizations (id, name, slug, created_at) VALUES ('default', 'Default', 'default', ?)",
        (now,),
    )
    for table in org_tables:
        await conn.execute(
            f"UPDATE {table} SET organization_id = 'default' WHERE organization_id IS NULL"
        )
    await conn.commit()

    for table in org_tables:
        index_name = f"idx_{table}_org"
        if not await _index_exists(conn, index_name):
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}(organization_id)"
            )
    await conn.commit()


async def _007_departments_org_unique(conn: aiosqlite.Connection) -> None:
    # Rebuild departments table: replace global UNIQUE(code) with UNIQUE(organization_id, code).
    # Guard: check if constraint already correct by inspecting the table schema.
    cursor = await conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='departments'"
    )
    row = await cursor.fetchone()
    if row and "UNIQUE(organization_id, code)" in row[0]:
        return  # already migrated

    await conn.execute("PRAGMA foreign_keys=OFF")
    await conn.execute("DROP TABLE IF EXISTS departments_new")
    await conn.execute("""
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
    await conn.execute("""
        INSERT INTO departments_new (id, name, code, description, product_count, organization_id, created_at)
        SELECT id, name, code, description, product_count, COALESCE(organization_id, 'default'), created_at
        FROM departments
    """)
    await conn.execute("DROP TABLE departments")
    await conn.execute("ALTER TABLE departments_new RENAME TO departments")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(organization_id)")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.commit()


async def _008_po_status_rename(conn: aiosqlite.Connection) -> None:
    await conn.execute("UPDATE purchase_order_items SET status = 'ordered' WHERE status = 'pending'")
    await conn.execute("UPDATE purchase_orders SET status = 'ordered' WHERE status = 'pending'")
    await conn.commit()


async def _009_invoice_line_items(conn: aiosqlite.Connection) -> None:
    if not await _column_exists(conn, "invoice_line_items", "cost"):
        await conn.execute(
            "ALTER TABLE invoice_line_items ADD COLUMN cost REAL NOT NULL DEFAULT 0"
        )
    if not await _column_exists(conn, "invoice_line_items", "job_id"):
        await conn.execute("ALTER TABLE invoice_line_items ADD COLUMN job_id TEXT")
    await conn.commit()


async def _010_org_settings(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
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
    await conn.commit()
    for col_def, col_name in [
        ("xero_ap_account_code TEXT NOT NULL DEFAULT '800'", "xero_ap_account_code"),
        ("xero_tracking_category_id TEXT", "xero_tracking_category_id"),
        ("xero_tax_type TEXT NOT NULL DEFAULT ''", "xero_tax_type"),
    ]:
        if not await _column_exists(conn, "org_settings", col_name):
            await conn.execute(f"ALTER TABLE org_settings ADD COLUMN {col_def}")
    await conn.commit()


async def _011_memory_artifacts(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
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
    await conn.commit()


async def _012_oauth_states(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await conn.commit()


async def _013_agent_runs(conn: aiosqlite.Connection) -> None:
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default',
            user_id TEXT,
            agent_name TEXT NOT NULL,
            model TEXT NOT NULL,
            mode TEXT,
            user_message TEXT,
            response_text TEXT,
            tool_calls TEXT NOT NULL DEFAULT '[]',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT,
            error_kind TEXT,
            parent_run_id TEXT,
            handoff_from TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_org ON agent_runs(org_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at);
    """)
    await conn.commit()


# ── registry ──────────────────────────────────────────────────────────────────

_MIGRATIONS: list[tuple[str, object]] = [
    ("001_initial_schema", _001_initial_schema),
    ("002_vendor_barcode", _002_vendor_barcode),
    ("003_uom_columns", _003_uom_columns),
    ("004_sku_uniqueness", _004_sku_uniqueness),
    ("005_barcode_uniqueness", _005_barcode_uniqueness),
    ("006_multi_tenant", _006_multi_tenant),
    ("007_departments_org_unique", _007_departments_org_unique),
    ("008_po_status_rename", _008_po_status_rename),
    ("009_invoice_line_items", _009_invoice_line_items),
    ("010_org_settings", _010_org_settings),
    ("011_memory_artifacts", _011_memory_artifacts),
    ("012_oauth_states", _012_oauth_states),
    ("013_agent_runs", _013_agent_runs),
]


async def _ensure_tracking_table(conn: aiosqlite.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    await conn.commit()


async def _bootstrap_existing_db(conn: aiosqlite.Connection, versions: list[str]) -> bool:
    """Fast-forward migration history for DBs that existed before the runner was introduced.

    Detects a fully-migrated existing DB by checking for memory_artifacts (the last migration).
    Marks all migrations as applied without re-running them.
    """
    cursor = await conn.execute("SELECT COUNT(*) FROM schema_migrations")
    count = (await cursor.fetchone())[0]
    if count > 0:
        return False  # already has history — normal path

    if not await _table_exists(conn, "memory_artifacts"):
        return False  # fresh DB — run all migrations normally

    # Existing fully-migrated DB with no history yet — fast-forward.
    now = datetime.now(timezone.utc).isoformat()
    for version in versions:
        await conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, now),
        )
    await conn.commit()
    logger.info("Bootstrapped migration history for existing database (%d migrations recorded)", len(versions))
    return True


async def run_migrations(conn: aiosqlite.Connection) -> None:
    """Apply all pending migrations in order."""
    await _ensure_tracking_table(conn)

    all_versions = [v for v, _ in _MIGRATIONS]
    await _bootstrap_existing_db(conn, all_versions)

    cursor = await conn.execute("SELECT version FROM schema_migrations")
    applied = {row[0] for row in await cursor.fetchall()}

    for version, migrate_fn in _MIGRATIONS:
        if version in applied:
            continue
        logger.info("Applying migration %s", version)
        await migrate_fn(conn)
        await conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()
        logger.info("Migration %s applied", version)
