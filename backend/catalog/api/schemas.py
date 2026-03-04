from typing import Optional
from pydantic import BaseModel


class SuggestUomRequest(BaseModel):
    name: str
    description: Optional[str] = None
