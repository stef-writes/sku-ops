"""Identity context schema — users, organizations, auth, and org settings."""

TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'warehouse_manager',
        company TEXT,
        billing_entity TEXT,
        billing_entity_id TEXT,
        phone TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS org_settings (
        organization_id TEXT PRIMARY KEY,
        default_tax_rate REAL NOT NULL DEFAULT 0.10,
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

    """CREATE TABLE IF NOT EXISTS refresh_tokens (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        details TEXT,
        ip_address TEXT,
        organization_id TEXT,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS billing_entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_name TEXT NOT NULL DEFAULT '',
        contact_email TEXT NOT NULL DEFAULT '',
        billing_address TEXT NOT NULL DEFAULT '',
        payment_terms TEXT NOT NULL DEFAULT 'net_30',
        xero_contact_id TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(organization_id, name)
    )""",

    """CREATE TABLE IF NOT EXISTS addresses (
        id TEXT PRIMARY KEY,
        label TEXT NOT NULL DEFAULT '',
        line1 TEXT NOT NULL DEFAULT '',
        line2 TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT '',
        postal_code TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'US',
        billing_entity_id TEXT,
        job_id TEXT,
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS fiscal_periods (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        closed_by_id TEXT,
        closed_at TEXT,
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(organization_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_billing_entities_org ON billing_entities(organization_id, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_billing_entities_name ON billing_entities(organization_id, name)",
    "CREATE INDEX IF NOT EXISTS idx_addresses_org ON addresses(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_addresses_entity ON addresses(billing_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_addresses_job ON addresses(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_fiscal_periods_org ON fiscal_periods(organization_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_users_org_role ON users(organization_id, role)",
]

SEED: list[str] = [
    "INSERT INTO organizations (id, name, slug, created_at) VALUES ('default', 'Default', 'default', '2024-01-01T00:00:00+00:00') ON CONFLICT DO NOTHING",
]
