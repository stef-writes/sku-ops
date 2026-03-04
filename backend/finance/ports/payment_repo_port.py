"""Payment repository port — testable contract for payment persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PaymentRepoPort(Protocol):

    async def insert(self, payment_dict: dict) -> None: ...

    async def get_by_session_id(self, session_id: str) -> Optional[dict]: ...

    async def update_status(
        self, session_id: str, payment_status: str, status: str,
        paid_at: Optional[str] = None,
    ) -> None: ...
