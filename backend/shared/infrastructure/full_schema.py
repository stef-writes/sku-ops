"""Full schema — aggregated from bounded context schema modules.

Single source of truth for the database schema.  Used by the migration runner
to bootstrap a *fresh* PostgreSQL database in one shot.
Each context owns its own table definitions; this module collects them
in dependency order (shared infra first, then catalog, inventory, etc.).
"""

from assistant.infrastructure.schema import (
    INDEXES as _assistant_indexes,
)
from assistant.infrastructure.schema import (
    TABLES as _assistant_tables,
)
from catalog.infrastructure.schema import (
    INDEXES as _catalog_indexes,
)
from catalog.infrastructure.schema import (
    TABLES as _catalog_tables,
)
from documents.infrastructure.schema import (
    INDEXES as _documents_indexes,
)
from documents.infrastructure.schema import (
    TABLES as _documents_tables,
)
from finance.infrastructure.schema import (
    INDEXES as _finance_indexes,
)
from finance.infrastructure.schema import (
    TABLES as _finance_tables,
)
from inventory.infrastructure.schema import (
    INDEXES as _inventory_indexes,
)
from inventory.infrastructure.schema import (
    TABLES as _inventory_tables,
)
from jobs.infrastructure.schema import (
    INDEXES as _jobs_indexes,
)
from jobs.infrastructure.schema import (
    TABLES as _jobs_tables,
)
from operations.infrastructure.schema import (
    INDEXES as _operations_indexes,
)
from operations.infrastructure.schema import (
    TABLES as _operations_tables,
)
from purchasing.infrastructure.schema import (
    INDEXES as _purchasing_indexes,
)
from purchasing.infrastructure.schema import (
    TABLES as _purchasing_tables,
)
from shared.infrastructure.schema import (
    EXTENSIONS as _shared_extensions,
)
from shared.infrastructure.schema import (
    INDEXES as _shared_indexes,
)
from shared.infrastructure.schema import (
    SEED as _shared_seed,
)
from shared.infrastructure.schema import (
    TABLES as _shared_tables,
)

_ALL_TABLES: list[str] = (
    _shared_tables
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
    _shared_indexes
    + _catalog_indexes
    + _inventory_indexes
    + _operations_indexes
    + _finance_indexes
    + _purchasing_indexes
    + _documents_indexes
    + _jobs_indexes
    + _assistant_indexes
)

FULL_SCHEMA: list[str] = _shared_extensions + _ALL_TABLES + _ALL_INDEXES + _shared_seed

# Exported separately so the migration runner can interleave migrations between
# table creation and index creation (needed when migrations rename columns that
# existing indexes reference).
ALL_EXTENSIONS: list[str] = _shared_extensions
ALL_TABLES: list[str] = _ALL_TABLES
ALL_INDEXES: list[str] = _ALL_INDEXES
