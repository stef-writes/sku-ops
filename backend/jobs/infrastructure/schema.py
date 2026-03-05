"""Jobs context schema — job master data."""

TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        billing_entity_id TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        service_address TEXT NOT NULL DEFAULT '',
        notes TEXT,
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(organization_id, code)
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_org_code ON jobs(organization_id, code)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_org_status ON jobs(organization_id, status)",
]
