"""Kernel-level constants shared across all bounded contexts."""

# Seed / dev-only org ID. Used by seed scripts, dev auth endpoints, and test
# fixtures. Not a runtime fallback — application code must always receive an
# explicit org_id from the auth layer or ambient context.
DEFAULT_ORG_ID = "default"
