"""Ledger query facade — application-layer entry point for cross-context consumers.

Other bounded contexts import from here, never from finance.infrastructure directly.
"""

from finance.infrastructure.ledger_repo import (
    ar_aging,
    get_journal,
    product_margins,
    purchase_spend,
    reference_counts,
    summary_by_account,
    summary_by_billing_entity,
    summary_by_contractor,
    summary_by_department,
    summary_by_job,
    trend_series,
    trial_balance,
)

__all__ = [
    "ar_aging",
    "get_journal",
    "product_margins",
    "purchase_spend",
    "reference_counts",
    "summary_by_account",
    "summary_by_billing_entity",
    "summary_by_contractor",
    "summary_by_department",
    "summary_by_job",
    "trend_series",
    "trial_balance",
]
