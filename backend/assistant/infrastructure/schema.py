"""Assistant context schema — agent runs, memory artifacts, and embeddings."""

TABLES: list[str] = [
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
    """CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        org_id TEXT NOT NULL,
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
    # Persistent embedding store — pgvector-backed semantic search across
    # all entity types (products, vendors, POs, jobs, memory artifacts, tools).
    # Replaces in-memory NumPy matrices with durable, ANN-indexed vectors.
    """CREATE TABLE IF NOT EXISTS embeddings (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        embedding vector(1536) NOT NULL,
        updated_at TEXT NOT NULL
    )""",
]

INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_artifacts(org_id, user_id, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_artifacts(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_org ON agent_runs(org_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_name, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at)",
    # Embedding indexes — HNSW for fast approximate nearest-neighbor search,
    # plus a B-tree for scoped queries by org + entity type.
    "CREATE INDEX IF NOT EXISTS idx_embeddings_org_type ON embeddings(org_id, entity_type)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_entity ON embeddings(org_id, entity_type, entity_id)",
]
