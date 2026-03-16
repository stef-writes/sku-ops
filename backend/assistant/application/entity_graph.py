"""Entity graph traversal — Postgres-native, single-query per entity.

Uses the ``entity_edges`` VIEW (UNION ALL across all FK relationships) to
traverse the domain graph in a single round-trip per entity.  Supports
multi-hop via WITH RECURSIVE.

The VIEW is not materialized — Postgres pushes WHERE predicates through the
UNION ALL branches, so only the relevant tables are scanned.  At hardware-
store scale (~thousands of entities) this is sub-millisecond.

For the center node's properties we still need entity-specific queries
(since each table has different columns), but neighbors come from a single
query against the edge view + label lookups via LATERAL joins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared.infrastructure.database import get_connection, get_org_id

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """An entity in the graph."""

    entity_type: str
    entity_id: str
    label: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A relationship between two entities."""

    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphContext:
    """Result of a graph traversal — nodes and their connections."""

    center: GraphNode
    neighbors: list[GraphNode]
    edges: list[GraphEdge]

    def format_for_agent(self, max_neighbors: int = 8) -> str:
        """Format as concise text for agent context injection."""
        lines = [f"[{self.center.entity_type}] {self.center.label}"]
        props = self.center.properties
        if props:
            prop_strs = [f"{k}: {v}" for k, v in props.items() if v is not None]
            if prop_strs:
                lines.append(f"  {', '.join(prop_strs)}")

        by_relation: dict[str, list[str]] = {}
        for edge, node in zip(
            self.edges[:max_neighbors], self.neighbors[:max_neighbors], strict=False
        ):
            by_relation.setdefault(edge.relation, []).append(node.label)

        for relation, labels in by_relation.items():
            lines.append(f"  {relation}: {', '.join(labels)}")
        return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────


async def neighbors(
    entity_type: str,
    entity_id: str,
    depth: int = 1,
    relation_filter: list[str] | None = None,
) -> GraphContext | None:
    """Find neighbors of an entity up to *depth* hops.

    depth=1: direct connections (single query against entity_edges view).
    depth=2: two hops via WITH RECURSIVE.
    """
    try:
        if not await _view_exists():
            # Fallback to direct queries if view not yet created
            handler = _DIRECT_HANDLERS.get(entity_type)
            if handler:
                return await handler(entity_id, relation_filter)
            return None

        center = await _load_center(entity_type, entity_id)
        if not center:
            return None

        if depth <= 1:
            neighbor_rows = await _edges_one_hop(
                center.entity_type, center.entity_id, relation_filter
            )
        else:
            neighbor_rows = await _edges_recursive(
                center.entity_type, center.entity_id, depth, relation_filter
            )

        nodes, edges = await _hydrate_neighbors(center.entity_type, center.entity_id, neighbor_rows)
        return GraphContext(center=center, neighbors=nodes, edges=edges)

    except Exception as e:
        logger.warning("Graph traversal failed for %s:%s — %s", entity_type, entity_id, e)
        return None


async def multi_neighbors(
    entities: list[tuple[str, str]],
    relation_filter: list[str] | None = None,
) -> list[GraphContext]:
    """Traverse neighbors for multiple entities."""
    results = []
    for etype, eid in entities:
        ctx = await neighbors(etype, eid, relation_filter=relation_filter)
        if ctx:
            results.append(ctx)
    return results


# ── View availability check ───────────────────────────────────────────────────

_view_ok: bool | None = None


async def _view_exists() -> bool:
    global _view_ok
    if _view_ok is not None:
        return _view_ok
    try:
        conn = get_connection()
        cur = await conn.execute(
            "SELECT 1 FROM information_schema.views WHERE table_name = 'entity_edges' LIMIT 1"
        )
        row = await cur.fetchone()
        _view_ok = row is not None
    except Exception:
        _view_ok = False
    return _view_ok


# ── Center node loaders (entity-specific, one query each) ────────────────────


async def _load_center(entity_type: str, entity_id: str) -> GraphNode | None:
    """Load the center node with its properties."""
    loader = _CENTER_LOADERS.get(entity_type)
    if not loader:
        return GraphNode(entity_type, entity_id, entity_id)
    return await loader(entity_id)


async def _load_sku(entity_id: str) -> GraphNode | None:
    conn = get_connection()
    org_id = get_org_id()
    cur = await conn.execute(
        "SELECT id, sku, name, price, cost, quantity, min_stock, sell_uom "
        "FROM skus WHERE (id = $1 OR sku = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return GraphNode(
        "sku",
        r["id"],
        f"{r['sku']} — {r['name']}",
        {
            "price": r["price"],
            "cost": r["cost"],
            "stock": r["quantity"],
            "min_stock": r["min_stock"],
            "sell_uom": r["sell_uom"],
        },
    )


async def _load_vendor(entity_id: str) -> GraphNode | None:
    conn = get_connection()
    org_id = get_org_id()
    cur = await conn.execute(
        "SELECT id, name, contact_name, email, phone "
        "FROM vendors WHERE id = $1 AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return GraphNode(
        "vendor",
        r["id"],
        r["name"],
        {
            "contact": r["contact_name"],
            "email": r["email"],
        },
    )


async def _load_job(entity_id: str) -> GraphNode | None:
    conn = get_connection()
    org_id = get_org_id()
    cur = await conn.execute(
        "SELECT id, code, name, service_address, status "
        "FROM jobs WHERE (id = $1 OR code = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return GraphNode(
        "job",
        r["id"],
        f"Job {r['code']} — {r['name']}",
        {
            "address": r["service_address"],
            "status": r["status"],
        },
    )


async def _load_invoice(entity_id: str) -> GraphNode | None:
    conn = get_connection()
    org_id = get_org_id()
    cur = await conn.execute(
        "SELECT id, invoice_number, contact_name, status, total, amount_credited "
        "FROM invoices WHERE (id = $1 OR invoice_number = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return GraphNode(
        "invoice",
        r["id"],
        f"Invoice {r['invoice_number']} — {r['contact_name']}",
        {
            "status": r["status"],
            "total": r["total"],
            "credited": r["amount_credited"],
        },
    )


async def _load_po(entity_id: str) -> GraphNode | None:
    conn = get_connection()
    org_id = get_org_id()
    cur = await conn.execute(
        "SELECT id, vendor_name, document_date, total, status "
        "FROM purchase_orders WHERE id = $1 AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return GraphNode(
        "po",
        r["id"],
        f"PO {r['id'][:8]} — {r['vendor_name']}",
        {
            "date": r["document_date"],
            "total": r["total"],
            "status": r["status"],
        },
    )


_CENTER_LOADERS = {
    "sku": _load_sku,
    "product": _load_sku,
    "vendor": _load_vendor,
    "job": _load_job,
    "invoice": _load_invoice,
    "po": _load_po,
    "purchase_order": _load_po,
}


# ── Edge queries (single round-trip via entity_edges VIEW) ────────────────────


async def _edges_one_hop(
    source_type: str,
    source_id: str,
    relation_filter: list[str] | None = None,
) -> list[dict]:
    """Fetch direct neighbors in one query."""
    conn = get_connection()
    org_id = get_org_id()

    if relation_filter:
        placeholders = ", ".join(f"${i + 4}" for i in range(len(relation_filter)))
        cur = await conn.execute(
            f"SELECT DISTINCT target_id, target_type, relation "
            f"FROM entity_edges "
            f"WHERE source_id = $1 AND source_type = $2 AND org_id = $3 "
            f"  AND relation IN ({placeholders}) "
            f"LIMIT 25",
            (source_id, source_type, org_id, *relation_filter),
        )
    else:
        cur = await conn.execute(
            "SELECT DISTINCT target_id, target_type, relation "
            "FROM entity_edges "
            "WHERE source_id = $1 AND source_type = $2 AND org_id = $3 "
            "LIMIT 25",
            (source_id, source_type, org_id),
        )
    return [dict(r) for r in await cur.fetchall()]


async def _edges_recursive(
    source_type: str,
    source_id: str,
    max_depth: int = 2,
    relation_filter: list[str] | None = None,
) -> list[dict]:
    """Multi-hop traversal via WITH RECURSIVE."""
    conn = get_connection()
    org_id = get_org_id()

    # Build relation filter clause
    rel_clause = ""
    params: list = [source_id, source_type, org_id, max_depth]
    if relation_filter:
        placeholders = ", ".join(f"${i + 5}" for i in range(len(relation_filter)))
        rel_clause = f"AND e.relation IN ({placeholders})"
        params.extend(relation_filter)

    cur = await conn.execute(
        f"""
        WITH RECURSIVE traversal AS (
            -- Seed: direct neighbors
            SELECT e.target_id, e.target_type, e.relation,
                   1 AS depth
            FROM entity_edges e
            WHERE e.source_id = $1 AND e.source_type = $2 AND e.org_id = $3
                  {rel_clause}
            UNION
            -- Recurse: neighbors of neighbors
            SELECT e.target_id, e.target_type, e.relation,
                   t.depth + 1 AS depth
            FROM traversal t
            JOIN entity_edges e ON e.source_id = t.target_id
                                AND e.source_type = t.target_type
                                AND e.org_id = $3
                                {rel_clause}
            WHERE t.depth < $4
              AND e.target_id != $1  -- avoid cycles back to center
        )
        SELECT DISTINCT target_id, target_type, relation, depth
        FROM traversal
        ORDER BY depth, relation
        LIMIT 30
        """,
        tuple(params),
    )
    return [dict(r) for r in await cur.fetchall()]


# ── Neighbor hydration (labels from actual tables) ────────────────────────────


async def _hydrate_neighbors(
    center_type: str,
    center_id: str,
    edge_rows: list[dict],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Convert raw edge rows into labeled GraphNodes by looking up each target.

    Uses a single query per entity type (batched) to minimize round-trips.
    """
    # Group targets by type for batched loading
    by_type: dict[str, list[dict]] = {}
    for row in edge_rows:
        by_type.setdefault(row["target_type"], []).append(row)

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    for target_type, rows in by_type.items():
        target_ids = [r["target_id"] for r in rows]
        labels = await _batch_labels(target_type, target_ids)

        for row in rows:
            tid = row["target_id"]
            label = labels.get(tid, tid[:12])
            node = GraphNode(target_type, tid, label)
            nodes.append(node)
            edges.append(
                GraphEdge(
                    center_type,
                    center_id,
                    target_type,
                    tid,
                    row["relation"],
                )
            )

    return nodes, edges


async def _batch_labels(entity_type: str, ids: list[str]) -> dict[str, str]:
    """Fetch display labels for a batch of entity IDs. Single query per type."""
    if not ids:
        return {}
    conn = get_connection()
    org_id = get_org_id()

    # Build query based on entity type
    query_map = {
        "sku": (
            "SELECT id, sku || ' — ' || name AS label FROM skus "
            "WHERE id = ANY($1) AND organization_id = $2"
        ),
        "vendor": (
            "SELECT id, name AS label FROM vendors WHERE id = ANY($1) AND organization_id = $2"
        ),
        "department": (
            "SELECT id, name AS label FROM departments WHERE id = ANY($1) AND organization_id = $2"
        ),
        "po": (
            "SELECT id, 'PO ' || LEFT(id, 8) || ' — ' || vendor_name AS label "
            "FROM purchase_orders WHERE id = ANY($1) AND organization_id = $2"
        ),
        "job": (
            "SELECT id, 'Job ' || code || ' — ' || name AS label "
            "FROM jobs WHERE id = ANY($1) AND organization_id = $2"
        ),
        "invoice": (
            "SELECT id, 'Invoice ' || invoice_number || ' — ' || contact_name AS label "
            "FROM invoices WHERE id = ANY($1) AND organization_id = $2"
        ),
        "withdrawal": (
            "SELECT id, 'Withdrawal — ' || COALESCE(contractor_name, 'unknown') AS label "
            "FROM withdrawals WHERE id = ANY($1) AND organization_id = $2"
        ),
        "billing_entity": (
            "SELECT id, name AS label FROM billing_entities "
            "WHERE id = ANY($1) AND organization_id = $2"
        ),
        "payment": (
            "SELECT id, 'Payment $' || amount || ' (' || method || ')' AS label "
            "FROM payments WHERE id = ANY($1) AND organization_id = $2"
        ),
        "credit_note": (
            "SELECT id, 'CN ' || credit_note_number AS label "
            "FROM credit_notes WHERE id = ANY($1) AND organization_id = $2"
        ),
    }

    sql = query_map.get(entity_type)
    if not sql:
        return {eid: eid[:12] for eid in ids}

    cur = await conn.execute(sql, (ids, org_id))
    return {r["id"]: r["label"] for r in await cur.fetchall()}


# ── Direct query fallback (when entity_edges view doesn't exist yet) ──────────
# Simplified versions — just load center and basic neighbors.


async def _direct_sku(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    center = await _load_sku(entity_id)
    if not center:
        return GraphContext(GraphNode("sku", entity_id, entity_id), [], [])

    conn = get_connection()
    org_id = get_org_id()
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Vendors
    cur = await conn.execute(
        "SELECT vi.vendor_id, v.name "
        "FROM vendor_items vi JOIN vendors v ON v.id = vi.vendor_id "
        "WHERE vi.sku_id = $1 AND vi.organization_id = $2",
        (center.entity_id, org_id),
    )
    for r in await cur.fetchall():
        nodes.append(GraphNode("vendor", r["vendor_id"], r["name"]))
        edges.append(GraphEdge("sku", center.entity_id, "vendor", r["vendor_id"], "supplied_by"))

    return GraphContext(center, nodes, edges)


async def _direct_vendor(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    center = await _load_vendor(entity_id)
    if not center:
        return GraphContext(GraphNode("vendor", entity_id, entity_id), [], [])

    conn = get_connection()
    org_id = get_org_id()
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    cur = await conn.execute(
        "SELECT vi.sku_id, s.sku, s.name "
        "FROM vendor_items vi JOIN skus s ON s.id = vi.sku_id "
        "WHERE vi.vendor_id = $1 AND vi.organization_id = $2 LIMIT 15",
        (center.entity_id, org_id),
    )
    for r in await cur.fetchall():
        nodes.append(GraphNode("sku", r["sku_id"], f"{r['sku']} — {r['name']}"))
        edges.append(GraphEdge("vendor", center.entity_id, "sku", r["sku_id"], "supplies"))

    return GraphContext(center, nodes, edges)


_DIRECT_HANDLERS = {
    "sku": _direct_sku,
    "product": _direct_sku,
    "vendor": _direct_vendor,
}
