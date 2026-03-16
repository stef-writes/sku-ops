"""Entity graph traversal — follows FK relationships across bounded contexts.

Provides structural context to agents: given an entity, discover what's
connected to it (vendors supplying a product, POs for a vendor, invoices
for a job, etc.) via parameterized SQL queries against existing tables.

No materialized views or new tables — just efficient queries against the
existing schema.  Results are formatted for injection into agent context.
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


# ── Entity-specific queries ──────────────────────────────────────────────────
# Each returns (GraphNode for center, list of neighbors, list of edges).
# Queries are intentionally simple and use existing indexes.


async def neighbors(
    entity_type: str,
    entity_id: str,
    depth: int = 1,
    relation_filter: list[str] | None = None,
) -> GraphContext | None:
    """Find neighbors of an entity up to *depth* hops.

    Currently supports depth=1 (direct connections).  Deeper traversal
    can be added by recursing.
    """
    handler = _HANDLERS.get(entity_type)
    if not handler:
        logger.debug("No graph handler for entity_type=%s", entity_type)
        return None
    try:
        return await handler(entity_id, relation_filter)
    except Exception as e:
        logger.warning("Graph traversal failed for %s:%s — %s", entity_type, entity_id, e)
        return None


async def multi_neighbors(
    entities: list[tuple[str, str]],
    relation_filter: list[str] | None = None,
) -> list[GraphContext]:
    """Traverse neighbors for multiple entities. Returns list of contexts."""
    results = []
    for etype, eid in entities:
        ctx = await neighbors(etype, eid, relation_filter=relation_filter)
        if ctx:
            results.append(ctx)
    return results


# ── SKU / Product neighbors ──────────────────────────────────────────────────


async def _sku_neighbors(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    conn = get_connection()
    org_id = get_org_id()

    # Center node: the SKU
    cur = await conn.execute(
        "SELECT id, sku, name, price, cost, quantity, min_stock, sell_uom, "
        "category_id FROM skus WHERE (id = $1 OR sku = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return GraphContext(
            center=GraphNode("sku", entity_id, entity_id),
            neighbors=[],
            edges=[],
        )

    center = GraphNode(
        "sku",
        row["id"],
        f"{row['sku']} — {row['name']}",
        {
            "price": row["price"],
            "cost": row["cost"],
            "stock": row["quantity"],
            "min_stock": row["min_stock"],
            "sell_uom": row["sell_uom"],
        },
    )
    sku_id = row["id"]
    product_id = row.get("category_id")
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Vendors (via vendor_items)
    if not relation_filter or "supplied_by" in relation_filter:
        cur = await conn.execute(
            "SELECT vi.vendor_id, vi.cost, vi.lead_time_days, vi.is_preferred, "
            "v.name AS vendor_name "
            "FROM vendor_items vi JOIN vendors v ON v.id = vi.vendor_id "
            "WHERE vi.sku_id = $1 AND vi.organization_id = $2",
            (sku_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "vendor",
                r["vendor_id"],
                r["vendor_name"],
                {
                    "cost": r["cost"],
                    "lead_time": r["lead_time_days"],
                    "preferred": bool(r["is_preferred"]),
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("sku", sku_id, "vendor", r["vendor_id"], "supplied_by"))

    # Department
    if product_id and (not relation_filter or "in_department" in relation_filter):
        cur = await conn.execute("SELECT id, name FROM departments WHERE id = $1", (product_id,))
        dept = await cur.fetchone()
        if dept:
            nodes.append(GraphNode("department", dept["id"], dept["name"]))
            edges.append(GraphEdge("sku", sku_id, "department", dept["id"], "in_department"))

    # Recent POs containing this SKU (last 5)
    if not relation_filter or "ordered_in" in relation_filter:
        cur = await conn.execute(
            "SELECT DISTINCT po.id, po.vendor_name, po.document_date, po.status "
            "FROM purchase_order_items poi "
            "JOIN purchase_orders po ON po.id = poi.po_id "
            "WHERE poi.product_id = $1 AND po.organization_id = $2 "
            "ORDER BY po.document_date DESC LIMIT 5",
            (sku_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "po",
                r["id"],
                f"PO {r['id'][:8]} ({r['vendor_name']})",
                {
                    "date": r["document_date"],
                    "status": r["status"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("sku", sku_id, "po", r["id"], "ordered_in"))

    # Recent withdrawals (last 5)
    if not relation_filter or "withdrawn_in" in relation_filter:
        cur = await conn.execute(
            "SELECT w.id, w.job_id, w.contractor_name, w.created_at "
            "FROM withdrawal_items wi "
            "JOIN withdrawals w ON w.id = wi.withdrawal_id "
            "WHERE wi.product_id = $1 AND w.organization_id = $2 "
            "ORDER BY w.created_at DESC LIMIT 5",
            (sku_id, org_id),
        )
        for r in await cur.fetchall():
            label = f"Withdrawal for {r['contractor_name'] or 'unknown'}"
            if r["job_id"]:
                label += f" (job {r['job_id'][:8]})"
            n = GraphNode("withdrawal", r["id"], label, {"date": r["created_at"]})
            nodes.append(n)
            edges.append(GraphEdge("sku", sku_id, "withdrawal", r["id"], "withdrawn_in"))

    return GraphContext(center=center, neighbors=nodes, edges=edges)


# ── Vendor neighbors ─────────────────────────────────────────────────────────


async def _vendor_neighbors(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    conn = get_connection()
    org_id = get_org_id()

    cur = await conn.execute(
        "SELECT id, name, contact_name, email, phone "
        "FROM vendors WHERE id = $1 AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return GraphContext(
            center=GraphNode("vendor", entity_id, entity_id), neighbors=[], edges=[]
        )

    center = GraphNode(
        "vendor",
        row["id"],
        row["name"],
        {
            "contact": row["contact_name"],
            "email": row["email"],
        },
    )
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # SKUs supplied
    if not relation_filter or "supplies" in relation_filter:
        cur = await conn.execute(
            "SELECT vi.sku_id, vi.cost, vi.is_preferred, s.sku, s.name AS sku_name "
            "FROM vendor_items vi JOIN skus s ON s.id = vi.sku_id "
            "WHERE vi.vendor_id = $1 AND vi.organization_id = $2 LIMIT 15",
            (entity_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "sku",
                r["sku_id"],
                f"{r['sku']} — {r['sku_name']}",
                {
                    "cost": r["cost"],
                    "preferred": bool(r["is_preferred"]),
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("vendor", entity_id, "sku", r["sku_id"], "supplies"))

    # Recent POs
    if not relation_filter or "has_po" in relation_filter:
        cur = await conn.execute(
            "SELECT id, document_date, total, status "
            "FROM purchase_orders WHERE vendor_id = $1 AND organization_id = $2 "
            "ORDER BY document_date DESC LIMIT 5",
            (entity_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "po",
                r["id"],
                f"PO {r['id'][:8]} — ${r['total']:.2f}",
                {
                    "date": r["document_date"],
                    "status": r["status"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("vendor", entity_id, "po", r["id"], "has_po"))

    return GraphContext(center=center, neighbors=nodes, edges=edges)


# ── Job neighbors ─────────────────────────────────────────────────────────────


async def _job_neighbors(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    conn = get_connection()
    org_id = get_org_id()

    cur = await conn.execute(
        "SELECT id, code, name, service_address, status, billing_entity_id "
        "FROM jobs WHERE (id = $1 OR code = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return GraphContext(center=GraphNode("job", entity_id, entity_id), neighbors=[], edges=[])

    center = GraphNode(
        "job",
        row["id"],
        f"Job {row['code']} — {row['name']}",
        {
            "address": row["service_address"],
            "status": row["status"],
        },
    )
    job_id = row["id"]
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Withdrawals for this job
    if not relation_filter or "has_withdrawal" in relation_filter:
        cur = await conn.execute(
            "SELECT id, contractor_name, total, cost_total, created_at "
            "FROM withdrawals WHERE job_id = $1 AND organization_id = $2 "
            "ORDER BY created_at DESC LIMIT 10",
            (job_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "withdrawal",
                r["id"],
                f"Withdrawal — {r['contractor_name']}",
                {
                    "total": r["total"],
                    "cost": r["cost_total"],
                    "date": r["created_at"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("job", job_id, "withdrawal", r["id"], "has_withdrawal"))

    # Invoices referencing this job
    if not relation_filter or "has_invoice" in relation_filter:
        cur = await conn.execute(
            "SELECT DISTINCT i.id, i.invoice_number, i.total, i.status "
            "FROM invoice_line_items ili "
            "JOIN invoices i ON i.id = ili.invoice_id "
            "WHERE ili.job_id = $1 AND i.organization_id = $2 LIMIT 5",
            (job_id, org_id),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "invoice",
                r["id"],
                f"Invoice {r['invoice_number']} — ${r['total']:.2f}",
                {
                    "status": r["status"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("job", job_id, "invoice", r["id"], "has_invoice"))

    # Billing entity
    if row["billing_entity_id"] and (not relation_filter or "billed_to" in relation_filter):
        cur = await conn.execute(
            "SELECT id, name FROM billing_entities WHERE id = $1", (row["billing_entity_id"],)
        )
        be = await cur.fetchone()
        if be:
            nodes.append(GraphNode("billing_entity", be["id"], be["name"]))
            edges.append(GraphEdge("job", job_id, "billing_entity", be["id"], "billed_to"))

    return GraphContext(center=center, neighbors=nodes, edges=edges)


# ── Invoice neighbors ─────────────────────────────────────────────────────────


async def _invoice_neighbors(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    conn = get_connection()
    org_id = get_org_id()

    cur = await conn.execute(
        "SELECT id, invoice_number, billing_entity_id, contact_name, "
        "status, total, amount_credited "
        "FROM invoices WHERE (id = $1 OR invoice_number = $1) AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return GraphContext(
            center=GraphNode("invoice", entity_id, entity_id), neighbors=[], edges=[]
        )

    center = GraphNode(
        "invoice",
        row["id"],
        f"Invoice {row['invoice_number']} — {row['contact_name']}",
        {
            "status": row["status"],
            "total": row["total"],
            "credited": row["amount_credited"],
        },
    )
    inv_id = row["id"]
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Linked withdrawals
    if not relation_filter or "from_withdrawal" in relation_filter:
        cur = await conn.execute(
            "SELECT w.id, w.contractor_name, w.total, w.created_at "
            "FROM invoice_withdrawals iw "
            "JOIN withdrawals w ON w.id = iw.withdrawal_id "
            "WHERE iw.invoice_id = $1",
            (inv_id,),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "withdrawal", r["id"], f"Withdrawal — {r['contractor_name']}", {"total": r["total"]}
            )
            nodes.append(n)
            edges.append(GraphEdge("invoice", inv_id, "withdrawal", r["id"], "from_withdrawal"))

    # Payments
    if not relation_filter or "has_payment" in relation_filter:
        cur = await conn.execute(
            "SELECT id, amount, method, payment_date FROM payments WHERE invoice_id = $1",
            (inv_id,),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "payment",
                r["id"],
                f"Payment ${r['amount']:.2f} ({r['method']})",
                {
                    "date": r["payment_date"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("invoice", inv_id, "payment", r["id"], "has_payment"))

    # Credit notes
    if not relation_filter or "has_credit_note" in relation_filter:
        cur = await conn.execute(
            "SELECT id, credit_note_number, total, status FROM credit_notes WHERE invoice_id = $1",
            (inv_id,),
        )
        for r in await cur.fetchall():
            n = GraphNode(
                "credit_note",
                r["id"],
                f"CN {r['credit_note_number']} — ${r['total']:.2f}",
                {
                    "status": r["status"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("invoice", inv_id, "credit_note", r["id"], "has_credit_note"))

    return GraphContext(center=center, neighbors=nodes, edges=edges)


# ── PO neighbors ──────────────────────────────────────────────────────────────


async def _po_neighbors(entity_id: str, relation_filter: list[str] | None) -> GraphContext:
    conn = get_connection()
    org_id = get_org_id()

    cur = await conn.execute(
        "SELECT id, vendor_id, vendor_name, document_date, total, status "
        "FROM purchase_orders WHERE id = $1 AND organization_id = $2 LIMIT 1",
        (entity_id, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return GraphContext(center=GraphNode("po", entity_id, entity_id), neighbors=[], edges=[])

    center = GraphNode(
        "po",
        row["id"],
        f"PO {row['id'][:8]} — {row['vendor_name']}",
        {
            "date": row["document_date"],
            "total": row["total"],
            "status": row["status"],
        },
    )
    po_id = row["id"]
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Vendor
    if row["vendor_id"] and (not relation_filter or "from_vendor" in relation_filter):
        cur = await conn.execute("SELECT id, name FROM vendors WHERE id = $1", (row["vendor_id"],))
        v = await cur.fetchone()
        if v:
            nodes.append(GraphNode("vendor", v["id"], v["name"]))
            edges.append(GraphEdge("po", po_id, "vendor", v["id"], "from_vendor"))

    # Line items → SKUs
    if not relation_filter or "contains_sku" in relation_filter:
        cur = await conn.execute(
            "SELECT poi.product_id, poi.name, poi.ordered_qty, poi.delivered_qty, "
            "poi.unit_price, s.sku "
            "FROM purchase_order_items poi "
            "LEFT JOIN skus s ON s.id = poi.product_id "
            "WHERE poi.po_id = $1 AND poi.organization_id = $2 LIMIT 20",
            (po_id, org_id),
        )
        for r in await cur.fetchall():
            sku_label = r["sku"] or r["product_id"] or "unmatched"
            n = GraphNode(
                "sku",
                r["product_id"] or "",
                f"{sku_label} — {r['name']}",
                {
                    "ordered": r["ordered_qty"],
                    "delivered": r["delivered_qty"],
                    "unit_price": r["unit_price"],
                },
            )
            nodes.append(n)
            edges.append(GraphEdge("po", po_id, "sku", r["product_id"] or "", "contains_sku"))

    return GraphContext(center=center, neighbors=nodes, edges=edges)


# ── Handler registry ──────────────────────────────────────────────────────────

_HANDLERS = {
    "sku": _sku_neighbors,
    "product": _sku_neighbors,  # alias
    "vendor": _vendor_neighbors,
    "job": _job_neighbors,
    "invoice": _invoice_neighbors,
    "po": _po_neighbors,
    "purchase_order": _po_neighbors,  # alias
}
