"""Backward-compatible re-export — use finance.adapters.invoicing_factory instead."""
from finance.adapters.invoicing_factory import (  # noqa: F401
    get_invoicing_gateway,
    get_invoicing_gateway as get_xero_gateway,
)
