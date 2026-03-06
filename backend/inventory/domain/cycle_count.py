"""Cycle count domain — snapshot-based physical inventory counting."""
from enum import Enum
from typing import Optional

from kernel.entity import Entity


class CycleCountStatus(str, Enum):
    OPEN = "open"
    COMMITTED = "committed"


class CycleCount(Entity):
    """A counting session scoped to an org (and optionally a department)."""
    organization_id: str
    status: CycleCountStatus = CycleCountStatus.OPEN
    # None = full warehouse count; a department name scopes to that dept only.
    scope: str | None = None
    created_by_id: str
    created_by_name: str = ""
    committed_by_id: str | None = None
    committed_at: str | None = None


class CycleCountItem(Entity):
    """One product line within a cycle count session."""
    cycle_count_id: str
    product_id: str
    sku: str
    product_name: str = ""
    # Frozen at the moment the count was opened — never changes after that.
    snapshot_qty: float
    # Null until the counter physically enters a value.
    counted_qty: float | None = None
    # Computed at entry time: counted_qty - snapshot_qty.
    variance: float | None = None
    unit: str = "each"
    notes: str | None = None
