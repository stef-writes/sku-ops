"""Inventory context schema — stock transaction ledger and cycle counts."""

TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS stock_transactions (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        sku TEXT NOT NULL,
        product_name TEXT NOT NULL DEFAULT '',
        quantity_delta REAL NOT NULL,
        quantity_before REAL NOT NULL,
        quantity_after REAL NOT NULL,
        unit TEXT NOT NULL DEFAULT 'each',
        transaction_type TEXT NOT NULL,
        reference_id TEXT,
        reference_type TEXT,
        reason TEXT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL DEFAULT '',
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS cycle_counts (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        scope TEXT,
        created_by_id TEXT NOT NULL,
        created_by_name TEXT NOT NULL DEFAULT '',
        committed_by_id TEXT,
        committed_at TEXT,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS cycle_count_items (
        id TEXT PRIMARY KEY,
        cycle_count_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        sku TEXT NOT NULL,
        product_name TEXT NOT NULL DEFAULT '',
        snapshot_qty REAL NOT NULL,
        counted_qty REAL,
        variance REAL,
        unit TEXT NOT NULL DEFAULT 'each',
        notes TEXT,
        created_at TEXT NOT NULL
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_stock_product ON stock_transactions(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_created ON stock_transactions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_product_created ON stock_transactions(product_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_transactions_org ON stock_transactions(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_cycle_counts_org ON cycle_counts(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_cycle_counts_status ON cycle_counts(status)",
    "CREATE INDEX IF NOT EXISTS idx_cycle_count_items_count ON cycle_count_items(cycle_count_id)",
    "CREATE INDEX IF NOT EXISTS idx_cycle_count_items_product ON cycle_count_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_cycle_counts_org_status_created ON cycle_counts(organization_id, status, created_at)",
]
