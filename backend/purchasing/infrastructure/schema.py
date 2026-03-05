"""Purchasing context schema — purchase orders and line items."""

TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS purchase_orders (
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
        document_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        organization_id TEXT
    )""",

    """CREATE TABLE IF NOT EXISTS purchase_order_items (
        id TEXT PRIMARY KEY,
        po_id TEXT NOT NULL REFERENCES purchase_orders(id),
        name TEXT NOT NULL,
        original_sku TEXT,
        ordered_qty REAL NOT NULL DEFAULT 1,
        delivered_qty REAL,
        unit_price REAL NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0,
        base_unit TEXT NOT NULL DEFAULT 'each',
        sell_uom TEXT NOT NULL DEFAULT 'each',
        pack_qty INTEGER NOT NULL DEFAULT 1,
        suggested_department TEXT NOT NULL DEFAULT 'HDW',
        status TEXT NOT NULL DEFAULT 'ordered',
        product_id TEXT,
        organization_id TEXT
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_po_org_status ON purchase_orders(organization_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_po_created ON purchase_orders(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(po_id)",
    "CREATE INDEX IF NOT EXISTS idx_po_items_status ON purchase_order_items(status)",
]
