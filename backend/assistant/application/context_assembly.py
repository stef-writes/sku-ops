"""Context assembly pipeline — builds rich context for agents before dispatch.

Combines four sources into a single structured context block:
  1. Vector search — what entities match the user's query
  2. Entity graph — what's connected to those entities
  3. Semantic memory — relevant facts from prior sessions
  4. Session state — active entities and topic from current session

The assembled context is injected as a system message before the agent runs,
giving it structural awareness without needing discovery tool calls.

Used by both the unified agent and specialist agents.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from assistant.application.entity_graph import GraphContext, multi_neighbors

if TYPE_CHECKING:
    from assistant.application.session_state import EntityRef, SessionState

logger = logging.getLogger(__name__)


@dataclass
class AssembledContext:
    """Rich context assembled from multiple sources."""

    entity_hits: list[dict] = field(default_factory=list)
    graph_contexts: list[GraphContext] = field(default_factory=list)
    memory_context: str = ""
    active_entities: list[EntityRef] = field(default_factory=list)
    last_topic: str | None = None

    def format_for_agent(self) -> str | None:
        """Format as a concise context block for system prompt injection.

        Returns None if no meaningful context was assembled.
        """
        sections: list[str] = []

        # Graph context (entity + connections)
        if self.graph_contexts:
            entity_lines = []
            for gc in self.graph_contexts[:5]:
                entity_lines.append(gc.format_for_agent(max_neighbors=5))
            sections.append("[Relevant entities]\n" + "\n\n".join(entity_lines))

        # Semantic entity hits without graph (fallback)
        elif self.entity_hits:
            hit_lines = []
            for h in self.entity_hits[:5]:
                hit_lines.append(
                    f"- [{h['entity_type']}] {h.get('content', h['entity_id'])} "
                    f"(relevance: {h.get('similarity', 0):.2f})"
                )
            sections.append("[Potentially relevant entities]\n" + "\n".join(hit_lines))

        # Memory context
        if self.memory_context:
            sections.append(self.memory_context)

        # Active session entities
        if self.active_entities:
            active_lines = [f"- {e.type}: {e.label} ({e.id[:8]})" for e in self.active_entities[:5]]
            sections.append("[Active in this session]\n" + "\n".join(active_lines))

        # Last topic
        if self.last_topic:
            sections.append(f"[Current topic]: {self.last_topic}")

        if not sections:
            return None
        return "\n\n".join(sections)


async def assemble_context(
    query: str,
    user_id: str,
    session_state: SessionState | None = None,
    include_graph: bool = True,
    include_memory: bool = True,
    max_entity_hits: int = 5,
    max_memory_items: int = 8,
) -> AssembledContext:
    """Build rich context for an agent call.

    Runs vector search, graph traversal, and memory recall concurrently.
    Each source is independent — failures in one don't affect the others.
    """
    ctx = AssembledContext()

    if session_state:
        ctx.active_entities = session_state.entities[:5]
        ctx.last_topic = session_state.last_topic

    # Run independent lookups concurrently
    tasks = {}

    tasks["vector"] = asyncio.create_task(_vector_search(query, max_entity_hits))

    if include_memory:
        tasks["memory"] = asyncio.create_task(_recall_memory(user_id, query, max_memory_items))

    # Wait for vector search first (needed for graph traversal)
    entity_hits = await tasks["vector"]
    ctx.entity_hits = entity_hits

    # Graph traversal for top hits + active session entities
    if include_graph and (entity_hits or ctx.active_entities):
        graph_entities: list[tuple[str, str]] = []
        # From vector search hits
        for h in entity_hits[:3]:
            graph_entities.append((h["entity_type"], h["entity_id"]))
        # From active session state
        for e in ctx.active_entities[:2]:
            pair = (e.type, e.id)
            if pair not in graph_entities:
                graph_entities.append(pair)

        if graph_entities:
            try:
                ctx.graph_contexts = await multi_neighbors(graph_entities)
            except Exception as e:
                logger.debug("Graph traversal failed (non-critical): %s", e)

    # Collect memory result
    if "memory" in tasks:
        try:
            ctx.memory_context = await tasks["memory"]
        except Exception as e:
            logger.debug("Memory recall failed (non-critical): %s", e)

    return ctx


async def _vector_search(query: str, limit: int) -> list[dict]:
    """Search embeddings for relevant entities. Returns empty list on failure."""
    try:
        from assistant.infrastructure.embedding_store import (
            embed_query,
            is_pgvector_available,
            search,
        )
        from shared.infrastructure.db import get_org_id

        if not await is_pgvector_available():
            return []

        qvec = await embed_query(query)
        if qvec is None:
            return []

        org_id = get_org_id()
        # Search across domain entities (not memory — that's handled separately)
        hits = await search(
            qvec,
            org_id,
            entity_types=["sku", "vendor", "purchase_order", "job"],
            limit=limit,
        )
        # Filter low-relevance hits
        return [h for h in hits if h.get("similarity", 0) > 0.25]
    except Exception as e:
        logger.debug("Vector search failed (non-critical): %s", e)
        return []


async def _recall_memory(user_id: str, query: str, limit: int) -> str:
    """Recall semantic memory. Returns empty string on failure."""
    try:
        from assistant.agents.memory.store import recall

        return await recall(user_id=user_id, query=query, limit=limit)
    except Exception as e:
        logger.debug("Memory recall failed (non-critical): %s", e)
        return ""
