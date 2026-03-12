"""Material request processing — converts a pending request into a withdrawal."""

from datetime import UTC, datetime

from identity.application.user_service import get_user_by_id
from operations.application.queries import (
    get_material_request_by_id,
    mark_material_request_processed,
)
from operations.application.withdrawal_service import create_withdrawal_wired
from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.types import CurrentUser


class MaterialRequestError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


async def process_material_request(
    request_id: str,
    job_id_override: str | None,
    service_address_override: str | None,
    notes: str | None,
    current_user_id: str,
    current_user_name: str,
) -> dict:
    """Validate a pending material request, create a withdrawal, and mark it processed.

    Returns the created withdrawal dict.
    Raises MaterialRequestError on validation failure.
    """
    org_id = get_org_id()
    req = await get_material_request_by_id(request_id)
    if not req:
        raise MaterialRequestError("Material request not found", 404)
    if req.status != "pending":
        raise MaterialRequestError("Request already processed")

    contractor = await get_user_by_id(req.contractor_id)
    if not contractor or contractor.role != "contractor":
        raise MaterialRequestError("Contractor not found")
    if contractor.organization_id and contractor.organization_id != org_id:
        raise MaterialRequestError("Contractor belongs to different organization", 403)

    job_id = (job_id_override or req.job_id or "").strip()
    service_address = (service_address_override or req.service_address or "").strip()
    if not job_id:
        raise MaterialRequestError("Job ID is required")
    if not service_address:
        raise MaterialRequestError("Service address is required")

    withdrawal_data = MaterialWithdrawalCreate(
        items=[
            WithdrawalItem(**i.model_dump()) if hasattr(i, "model_dump") else WithdrawalItem(**i)
            for i in req.items
        ],
        job_id=job_id,
        service_address=service_address,
        notes=notes,
    )

    current_user = CurrentUser(
        id=current_user_id,
        name=current_user_name,
        email="",
        role="admin",
        organization_id=org_id,
    )

    async with transaction():
        withdrawal = await create_withdrawal_wired(
            withdrawal_data, contractor.model_dump(), current_user
        )
        await mark_material_request_processed(
            request_id=request_id,
            withdrawal_id=withdrawal["id"],
            processed_by_id=current_user_id,
            processed_at=datetime.now(UTC).isoformat(),
        )
    return withdrawal
