"""Full schema — aggregated from bounded context schema modules.

Single source of truth for the database schema.  Used by the migration runner
to bootstrap a *fresh* database (SQLite or PostgreSQL) in one shot.
Each context owns its own table definitions; this module collects them
in dependency order (identity first, then catalog, inventory, etc.).
"""
from identity.infrastructure.schema import (
    TABLES as _identity_tables,
    INDEXES as _identity_indexes,
    SEED as _identity_seed,
)
from catalog.infrastructure.schema import (
    TABLES as _catalog_tables,
    INDEXES as _catalog_indexes,
)
from inventory.infrastructure.schema import (
    TABLES as _inventory_tables,
    INDEXES as _inventory_indexes,
)
from operations.infrastructure.schema import (
    TABLES as _operations_tables,
    INDEXES as _operations_indexes,
)
from finance.infrastructure.schema import (
    TABLES as _finance_tables,
    INDEXES as _finance_indexes,
)
from purchasing.infrastructure.schema import (
    TABLES as _purchasing_tables,
    INDEXES as _purchasing_indexes,
)
from documents.infrastructure.schema import (
    TABLES as _documents_tables,
    INDEXES as _documents_indexes,
)
from jobs.infrastructure.schema import (
    TABLES as _jobs_tables,
    INDEXES as _jobs_indexes,
)
from assistant.infrastructure.schema import (
    TABLES as _assistant_tables,
    INDEXES as _assistant_indexes,
)

# Order matters: identity (orgs/users) first, then catalog (departments/products),
# then contexts that reference them.
_ALL_TABLES: list[str] = (
    _identity_tables
    + _catalog_tables
    + _inventory_tables
    + _operations_tables
    + _finance_tables
    + _purchasing_tables
    + _documents_tables
    + _jobs_tables
    + _assistant_tables
)

_ALL_INDEXES: list[str] = (
    _identity_indexes
    + _catalog_indexes
    + _inventory_indexes
    + _operations_indexes
    + _finance_indexes
    + _purchasing_indexes
    + _documents_indexes
    + _jobs_indexes
    + _assistant_indexes
)

FULL_SCHEMA: list[str] = _ALL_TABLES + _ALL_INDEXES + _identity_seed
