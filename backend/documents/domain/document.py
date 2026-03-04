from typing import List, Optional
from pydantic import BaseModel


class DocumentImportRequest(BaseModel):
    vendor_name: str
    create_vendor_if_missing: bool = True
    department_id: Optional[str] = None
    products: List[dict]
