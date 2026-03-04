"""Shared dependency type injected into all agent tool calls."""
from dataclasses import dataclass


@dataclass
class AgentDeps:
    org_id: str
    user_id: str
    user_name: str
