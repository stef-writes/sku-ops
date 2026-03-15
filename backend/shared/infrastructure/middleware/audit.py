"""Audit logging — records who-did-what for sensitive operations.

Usage in routes:

    from shared.api.deps import CurrentUserDep
    from shared.infrastructure.middleware.audit import audit_log

    @router.post("/some-sensitive-action")
    async def handler(request: Request, current_user: CurrentUserDep):
        # ... perform action ...
        await audit_log(
            user_id=current_user.id,
            action="payment.mark_paid",
            resource_type="withdrawal",
            resource_id=withdrawal_id,
            request=request,
            org_id=current_user.organization_id,
        )

This is intentionally a function, not global middleware, to avoid noisy logs
on read-only endpoints.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from shared.infrastructure.database import get_connection

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)


async def audit_log(
    *,
    user_id: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | str | None = None,
    request: Request | None = None,
    org_id: str | None = None,
) -> None:
    """Write an audit log entry to the database."""
    ip = ""
    if request:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip and request.client:
            ip = request.client.host

    details_str = json.dumps(details) if isinstance(details, dict) else (details or "")
    now = datetime.now(UTC).isoformat()

    try:
        conn = get_connection()
        await conn.execute(
            """INSERT INTO audit_log (id, user_id, action, resource_type, resource_id,
               details, ip_address, organization_id, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            (
                str(uuid.uuid4()),
                user_id,
                action,
                resource_type,
                resource_id,
                details_str,
                ip,
                org_id or "default",
                now,
            ),
        )
        await conn.commit()
    except Exception:
        logger.exception("Failed to write audit log entry")
