"""Shared infrastructure schema — cross-cutting tables not owned by any single context.

Includes: organizations (tenancy), users (auth — Supabase will replace),
refresh_tokens (auth), oauth_states (Xero flow), audit_log, billing_entities,
addresses, fiscal_periods, org_settings.
"""

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
        role TEXT NOT NULL DEFAULT 'admin',
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
        auto_invoice INTEGER NOT NULL DEFAULT 0,
        default_tax_rate REAL NOT NULL DEFAULT 0.10,
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
    """CREATE TABLE IF NOT EXISTS processed_events (
        event_id TEXT NOT NULL,
        handler_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        PRIMARY KEY (event_id, handler_name)
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_org_role ON users(organization_id, role)",
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
]

EXTENSIONS: list[str] = [
    "CREATE EXTENSION IF NOT EXISTS vector",
]

# ── Views (run after all tables + indexes) ────────────────────────────────────
# entity_edges: unified edge list across all bounded contexts.
# Enables single-query graph traversal with WITH RECURSIVE.
# A VIEW (not materialized) — always consistent, no refresh needed.
# For hardware-store scale (~thousands of entities), the query planner
# will push predicates through the UNION ALL and hit existing indexes.

VIEWS: list[str] = [
    """CREATE OR REPLACE VIEW entity_edges AS
    -- sku → vendor (via vendor_items)
    SELECT vi.sku_id       AS source_id,
           'sku'           AS source_type,
           vi.vendor_id    AS target_id,
           'vendor'        AS target_type,
           'supplied_by'   AS relation,
           vi.organization_id AS org_id
    FROM vendor_items vi
    UNION ALL
    -- vendor → sku (reverse)
    SELECT vi.vendor_id    AS source_id,
           'vendor'        AS source_type,
           vi.sku_id       AS target_id,
           'sku'           AS target_type,
           'supplies'      AS relation,
           vi.organization_id AS org_id
    FROM vendor_items vi
    UNION ALL
    -- sku → department
    SELECT s.id            AS source_id,
           'sku'           AS source_type,
           s.category_id   AS target_id,
           'department'    AS target_type,
           'in_department' AS relation,
           s.organization_id AS org_id
    FROM skus s WHERE s.category_id IS NOT NULL
    UNION ALL
    -- po → vendor
    SELECT po.id           AS source_id,
           'po'            AS source_type,
           po.vendor_id    AS target_id,
           'vendor'        AS target_type,
           'from_vendor'   AS relation,
           po.organization_id AS org_id
    FROM purchase_orders po WHERE po.vendor_id IS NOT NULL
    UNION ALL
    -- po_item → sku
    SELECT poi.po_id       AS source_id,
           'po'            AS source_type,
           poi.product_id  AS target_id,
           'sku'           AS target_type,
           'contains_sku'  AS relation,
           poi.organization_id AS org_id
    FROM purchase_order_items poi WHERE poi.product_id IS NOT NULL
    UNION ALL
    -- withdrawal → job
    SELECT w.id            AS source_id,
           'withdrawal'    AS source_type,
           w.job_id        AS target_id,
           'job'           AS target_type,
           'for_job'       AS relation,
           w.organization_id AS org_id
    FROM withdrawals w WHERE w.job_id IS NOT NULL
    UNION ALL
    -- job → withdrawal (reverse)
    SELECT w.job_id        AS source_id,
           'job'           AS source_type,
           w.id            AS target_id,
           'withdrawal'    AS target_type,
           'has_withdrawal' AS relation,
           w.organization_id AS org_id
    FROM withdrawals w WHERE w.job_id IS NOT NULL
    UNION ALL
    -- withdrawal → invoice (via join table)
    SELECT iw.withdrawal_id AS source_id,
           'withdrawal'     AS source_type,
           iw.invoice_id    AS target_id,
           'invoice'        AS target_type,
           'invoiced_in'    AS relation,
           i.organization_id AS org_id
    FROM invoice_withdrawals iw
    JOIN invoices i ON i.id = iw.invoice_id
    UNION ALL
    -- invoice → withdrawal (reverse)
    SELECT iw.invoice_id    AS source_id,
           'invoice'        AS source_type,
           iw.withdrawal_id AS target_id,
           'withdrawal'     AS target_type,
           'from_withdrawal' AS relation,
           i.organization_id AS org_id
    FROM invoice_withdrawals iw
    JOIN invoices i ON i.id = iw.invoice_id
    UNION ALL
    -- invoice → billing_entity
    SELECT i.id             AS source_id,
           'invoice'        AS source_type,
           i.billing_entity_id AS target_id,
           'billing_entity' AS target_type,
           'billed_to'      AS relation,
           i.organization_id AS org_id
    FROM invoices i WHERE i.billing_entity_id IS NOT NULL
    UNION ALL
    -- invoice → payment
    SELECT p.invoice_id    AS source_id,
           'invoice'       AS source_type,
           p.id            AS target_id,
           'payment'       AS target_type,
           'has_payment'   AS relation,
           p.organization_id AS org_id
    FROM payments p WHERE p.invoice_id IS NOT NULL
    UNION ALL
    -- invoice → credit_note
    SELECT cn.invoice_id   AS source_id,
           'invoice'       AS source_type,
           cn.id           AS target_id,
           'credit_note'   AS target_type,
           'has_credit_note' AS relation,
           cn.organization_id AS org_id
    FROM credit_notes cn WHERE cn.invoice_id IS NOT NULL
    UNION ALL
    -- withdrawal_item → sku
    SELECT wi.withdrawal_id AS source_id,
           'withdrawal'     AS source_type,
           wi.product_id    AS target_id,
           'sku'            AS target_type,
           'contains_sku'   AS relation,
           wi.organization_id AS org_id
    FROM withdrawal_items wi WHERE wi.product_id IS NOT NULL
    UNION ALL
    -- job → billing_entity
    SELECT j.id            AS source_id,
           'job'           AS source_type,
           j.billing_entity_id AS target_id,
           'billing_entity' AS target_type,
           'billed_to'     AS relation,
           j.organization_id AS org_id
    FROM jobs j WHERE j.billing_entity_id IS NOT NULL
    UNION ALL
    -- job → invoice (via line items)
    SELECT ili.job_id      AS source_id,
           'job'           AS source_type,
           ili.invoice_id  AS target_id,
           'invoice'       AS target_type,
           'has_invoice'   AS relation,
           i.organization_id AS org_id
    FROM invoice_line_items ili
    JOIN invoices i ON i.id = ili.invoice_id
    WHERE ili.job_id IS NOT NULL
    """,
]

SEED: list[str] = [
    "INSERT INTO organizations (id, name, slug, created_at) VALUES ('default', 'Default', 'default', '2024-01-01T00:00:00+00:00') ON CONFLICT DO NOTHING",
]
