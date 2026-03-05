"""Documents context schema — persistent document archive."""

TABLES: list[str] = [
    """CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        document_type TEXT NOT NULL DEFAULT 'other',
        vendor_name TEXT,
        file_hash TEXT NOT NULL DEFAULT '',
        file_size INTEGER NOT NULL DEFAULT 0,
        mime_type TEXT NOT NULL DEFAULT '',
        parsed_data TEXT,
        po_id TEXT,
        status TEXT NOT NULL DEFAULT 'parsed',
        uploaded_by_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_documents_org ON documents(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_po ON documents(po_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_vendor ON documents(vendor_name)",
    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)",
]
