"""PostgreSQL full schema — equivalent to SQLite migrations 001-013.

Used by the runner to bootstrap a fresh PostgreSQL database in one shot.
Each element is a single SQL statement (no multi-statement strings).
"""

PG_FULL_SCHEMA: list[str] = [
    # ── users ─────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'warehouse_manager',
        company TEXT,
        billing_entity TEXT,
        phone TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)",

    # ── departments ───────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS departments (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        code TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        product_count INTEGER NOT NULL DEFAULT 0,
        organization_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(organization_id, code)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_departments_org ON departments(organization_id)",

    # ── vendors ───────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS vendors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        product_count INTEGER NOT NULL DEFAULT 0,
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_vendors_org ON vendors(organization_id)",

    # ── products ──────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        sku TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        price REAL NOT NULL,
        cost REAL NOT NULL DEFAULT 0,
        quantity REAL NOT NULL DEFAULT 0,
        min_stock INTEGER NOT NULL DEFAULT 5,
        department_id TEXT NOT NULL REFERENCES departments(id),
        department_name TEXT NOT NULL DEFAULT '',
        vendor_id TEXT,
        vendor_name TEXT NOT NULL DEFAULT '',
        original_sku TEXT,
        barcode TEXT,
        vendor_barcode TEXT,
        base_unit TEXT NOT NULL DEFAULT 'each',
        sell_uom TEXT NOT NULL DEFAULT 'each',
        pack_qty INTEGER NOT NULL DEFAULT 1,
        organization_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON products(sku)",
    "CREATE INDEX IF NOT EXISTS idx_products_department ON products(department_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_vendor ON products(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_vendor_original_sku ON products(vendor_id, original_sku)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode) WHERE barcode IS NOT NULL AND TRIM(barcode) != ''",
    "CREATE INDEX IF NOT EXISTS idx_products_vendor_barcode ON products(vendor_barcode) WHERE vendor_barcode IS NOT NULL AND TRIM(vendor_barcode) != ''",
    "CREATE INDEX IF NOT EXISTS idx_products_org ON products(organization_id)",

    # ── withdrawals ───────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS withdrawals (
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
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_withdrawals_contractor ON withdrawals(contractor_id)",
    "CREATE INDEX IF NOT EXISTS idx_withdrawals_created ON withdrawals(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(payment_status)",
    "CREATE INDEX IF NOT EXISTS idx_withdrawals_billing ON withdrawals(billing_entity)",
    "CREATE INDEX IF NOT EXISTS idx_withdrawals_org ON withdrawals(organization_id)",

    # ── sku_counters ──────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS sku_counters (
        department_code TEXT PRIMARY KEY,
        counter INTEGER NOT NULL DEFAULT 0
    )""",

    # ── stock_transactions ────────────────────────────────────────────────
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
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_stock_product ON stock_transactions(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_created ON stock_transactions(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_product_created ON stock_transactions(product_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_transactions_org ON stock_transactions(organization_id)",

    # ── invoices ──────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS invoices (
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
        organization_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_billing ON invoices(billing_entity)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_org ON invoices(organization_id)",

    # ── invoice_withdrawals ───────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS invoice_withdrawals (
        invoice_id TEXT NOT NULL REFERENCES invoices(id),
        withdrawal_id TEXT NOT NULL REFERENCES withdrawals(id),
        PRIMARY KEY (invoice_id, withdrawal_id)
    )""",

    # ── invoice_line_items ────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS invoice_line_items (
        id TEXT PRIMARY KEY,
        invoice_id TEXT NOT NULL REFERENCES invoices(id),
        description TEXT NOT NULL DEFAULT '',
        quantity REAL NOT NULL,
        unit_price REAL NOT NULL,
        amount REAL NOT NULL,
        cost REAL NOT NULL DEFAULT 0,
        product_id TEXT,
        job_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_invoice_line_items_invoice ON invoice_line_items(invoice_id)",

    # ── invoice_counters ──────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS invoice_counters (
        key TEXT PRIMARY KEY,
        counter INTEGER NOT NULL DEFAULT 0
    )""",

    # ── organizations ─────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )""",

    # ── material_requests ─────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS material_requests (
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_material_requests_contractor ON material_requests(contractor_id)",
    "CREATE INDEX IF NOT EXISTS idx_material_requests_status ON material_requests(status)",
    "CREATE INDEX IF NOT EXISTS idx_material_requests_org ON material_requests(organization_id)",

    # ── purchase_orders ───────────────────────────────────────────────────
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
        created_at TEXT NOT NULL,
        updated_at TEXT,
        organization_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_po_org_status ON purchase_orders(organization_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_po_created ON purchase_orders(created_at)",

    # ── purchase_order_items ──────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS purchase_order_items (
        id TEXT PRIMARY KEY,
        po_id TEXT NOT NULL REFERENCES purchase_orders(id),
        name TEXT NOT NULL,
        original_sku TEXT,
        ordered_qty REAL NOT NULL DEFAULT 1,
        delivered_qty REAL,
        price REAL NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0,
        base_unit TEXT NOT NULL DEFAULT 'each',
        sell_uom TEXT NOT NULL DEFAULT 'each',
        pack_qty INTEGER NOT NULL DEFAULT 1,
        suggested_department TEXT NOT NULL DEFAULT 'HDW',
        status TEXT NOT NULL DEFAULT 'ordered',
        product_id TEXT,
        organization_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(po_id)",
    "CREATE INDEX IF NOT EXISTS idx_po_items_status ON purchase_order_items(status)",

    # ── org_settings ──────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS org_settings (
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
        xero_ap_account_code TEXT NOT NULL DEFAULT '800',
        xero_tracking_category_id TEXT,
        xero_tax_type TEXT NOT NULL DEFAULT '',
        updated_at TEXT
    )""",

    # ── memory_artifacts ──────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS memory_artifacts (
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_artifacts(org_id, user_id, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_artifacts(session_id)",

    # ── oauth_states ──────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",

    # ── agent_runs ────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS agent_runs (
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_org ON agent_runs(org_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_name, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at)",

    # ── seed default org ──────────────────────────────────────────────────
    "INSERT INTO organizations (id, name, slug, created_at) VALUES ('default', 'Default', 'default', '2024-01-01T00:00:00+00:00') ON CONFLICT DO NOTHING",
]
