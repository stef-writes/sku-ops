"""Stock repository port — testable contract for stock transaction persistence."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class StockRepoPort(Protocol):

    async def insert_transaction(self, tx_dict: dict, conn=None) -> None: ...

    async def list_by_product(self, product_id: str, limit: int = 50) -> list: ...
