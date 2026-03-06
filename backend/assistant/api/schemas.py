from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    mode: Literal["fast", "deep"] = "fast"
    agent_type: Literal["auto", "inventory", "ops", "finance"] = "auto"
