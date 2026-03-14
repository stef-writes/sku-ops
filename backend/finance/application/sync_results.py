"""Typed result models for Xero sync operations."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InvoiceSyncResult:
    """Result of syncing a single invoice or COGS repost to Xero."""

    invoice_id: str
    success: bool
    invoice_number: str | None = None
    xero_invoice_id: str | None = None
    xero_journal_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class POBillSyncResult:
    """Result of syncing a single PO as a Xero Bill."""

    po_id: str
    success: bool
    skipped: bool = False
    reason: str | None = None
    xero_bill_id: str | None = None
    error: str | None = None


@dataclass
class SyncError:
    """One error entry within a sync pass."""

    type: str
    id: str
    error: str | None = None
    number: str | None = None
    vendor: str | None = None


@dataclass
class SyncPassResult:
    """Outbound sync pass summary (invoices, credit notes, PO bills, or COGS reposts)."""

    synced: int = 0
    reposted: int = 0
    failed: int = 0
    errors: list[SyncError] = field(default_factory=list)


@dataclass
class ReconcilePassResult:
    """Reconciliation pass summary (compare local vs Xero)."""

    verified: int = 0
    mismatch: int = 0
    errors: list[SyncError] = field(default_factory=list)


@dataclass(frozen=True)
class XeroSyncSummary:
    """Full nightly sync summary returned by run_sync()."""

    org_id: str
    invoices_synced: int
    invoices_failed: int
    cogs_reposted: int
    cogs_repost_failed: int
    credit_notes_synced: int
    credit_notes_failed: int
    po_bills_synced: int
    po_bills_failed: int
    invoices_verified: int
    invoices_mismatch: int
    credit_notes_verified: int
    credit_notes_mismatch: int
    errors: list[SyncError]
