from typing import Literal, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # omit to start a new session
    mode: Literal["fast", "deep"] = "fast"
    agent_type: Literal["general", "inventory", "ops", "finance", "insights"] = "general"
