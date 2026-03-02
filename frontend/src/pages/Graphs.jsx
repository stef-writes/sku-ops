/**
 * Graphs.jsx — System visualization for Supply Yard
 *
 * Three D3 graphs, each chosen for what D3 does best:
 *
 *  1. Domain Model (force-directed KG)
 *     Product is the gravitational center. Every entity orbits it.
 *     Force simulation reveals semantic weight: tightly-linked entities cluster.
 *     Graph-RAG substrate: the schema the AI reasons over.
 *
 *  2. Operational Flow (structured DAG)
 *     Fixed left→right layout mirrors the physical warehouse.
 *     Goods arrive on the left, sit in stock center, leave right.
 *     Finance floats above. DAG topology = workflow topology.
 *
 *  3. Agent Architecture (hierarchical layout)
 *     Four fixed rows: query entry → dispatcher → specialists → data.
 *     Vertical axis = abstraction stack. Horizontal = domain grouping.
 *     Shows how a user message becomes a database query.
 */
import { useRef, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as d3 from "d3";
import { Network, GitBranch, Cpu, ChevronRight, MessageSquare, X, Loader2, ArrowLeft } from "lucide-react";

const BG   = "#0c1220";
const CARD = "#111827";
const SURF = "#1f2937";
const LINE = "#374151";
const TEXT = "#f9fafb";
const MUTED= "#6b7280";

// ─── helpers ────────────────────────────────────────────────────────────────
function rectEdge(cx, cy, hw, hh, tx, ty, pad = 0) {
  const dx = tx - cx, dy = ty - cy;
  if (!dx && !dy) return { x: cx + hw + pad, y: cy };
  const sx = Math.abs(dx) / (hw + pad), sy = Math.abs(dy) / (hh + pad);
  const t  = 1 / Math.max(sx, sy);
  return { x: cx + dx * t, y: cy + dy * t };
}

function curvePath(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2;
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
}

function addArrow(defs, id, color) {
  defs.append("marker").attr("id", id)
    .attr("viewBox", "0 -5 10 10").attr("refX", 9).attr("refY", 0)
    .attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
    .append("path").attr("d", "M0,-5L10,0L0,5")
    .attr("fill", color).attr("opacity", 0.7);
}

// Responsive container size hook
function useSize() {
  const ref = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return [ref, size];
}

// ════════════════════════════════════════════════════════════════════════════
// 1. DOMAIN MODEL — force-directed knowledge graph
// ════════════════════════════════════════════════════════════════════════════
const KG_NODES = [
  { id: "product",    label: "Product",        r: 44, color: "#10b981",
    props: "id · sku · name · qty_on_hand · cost · uom · reorder_point · barcode",
    desc:  "The core inventory unit. Every operation — receiving, issuing, ordering — touches a Product." },
  { id: "vendor",     label: "Vendor",          r: 33, color: "#f59e0b",
    props: "id · name · email · phone · org_id",
    desc:  "Supplier of products. Linked to purchase orders and invoices." },
  { id: "dept",       label: "Department",      r: 29, color: "#6366f1",
    props: "id · name · code · org_id",
    desc:  "Category bucket for products. Used for filtering, reporting, and AI activity queries." },
  { id: "po",         label: "Purchase Order",  r: 33, color: "#8b5cf6",
    props: "id · status · vendor_id · expected_date · total",
    desc:  "An order to a vendor. Contains line items (products + quantities). Triggers receiving." },
  { id: "invoice",    label: "Invoice",         r: 31, color: "#f43f5e",
    props: "id · vendor_id · po_id · amount · due_date · paid",
    desc:  "A vendor bill. Linked to a PO for reconciliation. Outstanding = accounts payable." },
  { id: "contractor", label: "Contractor",      r: 29, color: "#06b6d4",
    props: "id · name · company · role · org_id",
    desc:  "A field worker who requests and receives materials. Has a job history." },
  { id: "withdrawal", label: "Withdrawal",      r: 29, color: "#f97316",
    props: "id · product_id · qty · contractor_id · job_ref · date",
    desc:  "A stock-out event. Created when materials are issued. Decrements product qty." },
  { id: "request",    label: "Mat. Request",    r: 27, color: "#84cc16",
    props: "id · contractor_id · status · items[] · notes",
    desc:  "A pre-approval request from a contractor. Approved requests become withdrawals." },
];

const KG_EDGES = [
  { s: "product",    t: "dept",        label: "belongs_to",   d: 160, str: 0.7 },
  { s: "product",    t: "vendor",      label: "sourced_from", d: 175, str: 0.5 },
  { s: "po",         t: "vendor",      label: "ordered_from", d: 150, str: 0.7 },
  { s: "po",         t: "product",     label: "contains",     d: 170, str: 0.5 },
  { s: "invoice",    t: "vendor",      label: "issued_by",    d: 135, str: 0.6 },
  { s: "invoice",    t: "po",          label: "reconciles",   d: 125, str: 0.6 },
  { s: "withdrawal", t: "product",     label: "depletes",     d: 160, str: 0.7 },
  { s: "withdrawal", t: "contractor",  label: "issued_to",    d: 135, str: 0.7 },
  { s: "request",    t: "contractor",  label: "submitted_by", d: 135, str: 0.7 },
  { s: "request",    t: "product",     label: "requests",     d: 165, str: 0.5 },
  { s: "request",    t: "withdrawal",  label: "resolves_to",  d: 120, str: 0.5 },
];

function DomainModel({ selected, setSelected, w, h }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);

  useEffect(() => {
    if (!w || !h || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.append("rect").attr("width", w).attr("height", h).attr("fill", BG);

    const defs = svg.append("defs");
    KG_NODES.forEach(n => addArrow(defs, `kg-${n.id}`, n.color));

    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.3, 4])
      .on("zoom", evt => g.attr("transform", evt.transform)));

    const ringR = Math.min(w, h) * 0.28;
    const nodes = KG_NODES.map((n, i) => {
      const angle = i === 0 ? 0 : ((i - 1) / (KG_NODES.length - 1)) * Math.PI * 2;
      return {
        ...n,
        x: i === 0 ? w/2 : w/2 + Math.cos(angle) * ringR,
        y: i === 0 ? h/2 : h/2 + Math.sin(angle) * ringR * 0.82,
      };
    });
    nodes[0].fx = w/2; nodes[0].fy = h/2;

    const links = KG_EDGES.map(e => ({
      ...e, source: nodes.find(n => n.id === e.s), target: nodes.find(n => n.id === e.t),
    }));

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.d * Math.min(w, h) / 490).strength(d => d.str))
      .force("charge", d3.forceManyBody().strength(-900))
      .force("center", d3.forceCenter(w/2, h/2))
      .force("collide", d3.forceCollide(d => d.r + 28));
    simRef.current = sim;

    const pathG = g.append("g");
    const labelG = g.append("g");
    const nodeG  = g.append("g");

    const paths = pathG.selectAll("path").data(links).join("path")
      .attr("fill", "none").attr("stroke-width", 1.5)
      .attr("marker-end", d => `url(#kg-${d.t})`);

    const edgeLabels = labelG.selectAll("text").data(links).join("text")
      .attr("text-anchor", "middle").attr("font-size", 9)
      .attr("font-family", "ui-monospace, monospace").attr("font-weight", 500);

    const groups = nodeG.selectAll("g").data(nodes).join("g").style("cursor", "grab")
      .call(d3.drag()
        .on("start", (evt, d) => { if (!evt.active) sim.alphaTarget(0.25).restart(); d.fx=d.x; d.fy=d.y; })
        .on("drag",  (evt, d) => { d.fx=evt.x; d.fy=evt.y; })
        .on("end",   (evt, d) => { if (!evt.active) sim.alphaTarget(0); if (d.id!=="product"){d.fx=null;d.fy=null;} }));

    groups.append("circle").attr("r", d => d.r + 10).attr("fill", d => d.color).attr("opacity", 0.06);
    groups.append("circle").attr("r", d => d.r).attr("fill", SURF)
      .attr("stroke", d => d.color).attr("stroke-width", 2).attr("class", "kg-circle");
    groups.append("text").attr("text-anchor", "middle").attr("dy", "0.35em")
      .attr("font-size", d => d.r > 38 ? 14 : 11).attr("font-weight", 700)
      .attr("font-family", "Inter, ui-sans-serif, sans-serif").attr("pointer-events", "none")
      .attr("fill", TEXT).text(d => d.label);

    groups.on("click", (evt, d) => {
      setSelected(prev => prev === d.id ? null : d.id);
    }).on("mouseenter", (evt) => {
      d3.select(evt.currentTarget).select(".kg-circle").attr("stroke-width", 3.5);
    }).on("mouseleave", (evt) => {
      d3.select(evt.currentTarget).select(".kg-circle").attr("stroke-width", 2);
    });

    sim.on("tick", () => {
      paths.attr("d", d => {
        const dr = Math.sqrt((d.target.x-d.source.x)**2+(d.target.y-d.source.y)**2)*1.35;
        return `M${d.source.x},${d.source.y} A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
      }).attr("stroke", d => {
        const isSel = selected && (d.s === selected || d.t === selected);
        return (selected && !isSel) ? LINE : d.source.color;
      }).attr("stroke-opacity", d => {
        const isSel = selected && (d.s === selected || d.t === selected);
        return selected ? (isSel ? 0.8 : 0.04) : 0.4;
      });

      edgeLabels
        .attr("x", d => (d.source.x + d.target.x)/2)
        .attr("y", d => (d.source.y + d.target.y)/2 - 9)
        .attr("fill", d => {
          const isSel = selected && (d.s === selected || d.t === selected);
          return selected ? (isSel ? d.source.color : "transparent") : MUTED;
        }).text(d => d.label);

      groups.attr("transform", d => `translate(${d.x},${d.y})`)
        .attr("opacity", d => selected
          ? (selected === d.id || links.some(l=>(l.s===selected&&l.t===d.id)||(l.t===selected&&l.s===d.id)) ? 1 : 0.15)
          : 1);
    });

    svg.append("text").attr("x", 16).attr("y", h - 14)
      .attr("fill", LINE).attr("font-size", 9).attr("font-family", "Inter, ui-sans-serif, sans-serif")
      .text("drag · scroll to zoom · click to focus");

    return () => { sim.stop(); };
  }, [selected, setSelected, w, h]);

  return <svg ref={svgRef} width={w} height={h} style={{ display: "block", position: "absolute", inset: 0 }} />;
}

// ════════════════════════════════════════════════════════════════════════════
// 2. OPERATIONAL FLOW — structured DAG
// ════════════════════════════════════════════════════════════════════════════
// Design canvas these coords were authored in
const DW_OP = 980, DH_OP = 490;
const NW = 148, NH = 46;

const OP_NODES = [
  { id: "vendors",    label: "Vendors",           color: "#f59e0b", x: 72,  y: 262, w: NW,  h: NH,
    desc: "Supplier directory. Every company you buy from. Linked to POs and invoices.",
    ai:   ["Which vendor supplies pipe fittings?", "Show purchase history for vendor X"] },
  { id: "po",         label: "Purchase Orders",   color: "#8b5cf6", x: 248, y: 262, w: NW,  h: NH,
    desc: "Track orders sent to vendors. Mark received when goods arrive at the dock.",
    ai:   ["What POs are still open?", "What's expected from a vendor this week?"] },
  { id: "invoices",   label: "Invoices",           color: "#f43f5e", x: 195, y: 105, w: NW,  h: NH,
    desc: "Vendor bills tied to POs. What's paid, what's outstanding.",
    ai:   ["What invoices are overdue?", "Total owed to vendor X?"] },
  { id: "receive",    label: "Receive Inventory",  color: "#06b6d4", x: 422, y: 262, w: NW,  h: NH,
    desc: "Upload a delivery receipt or invoice — AI reads it, matches products, updates stock.",
    ai:   ["What came in today?", "Show receiving history for copper pipe"] },
  { id: "inventory",  label: "Inventory",          color: "#10b981", x: 605, y: 270, w: 162, h: 52,
    desc: "Live stock — every product, qty on hand, cost, UOM, and reorder point.",
    ai:   ["What's running low?", "Slow-moving items this month", "Reorder suggestions"] },
  { id: "depts",      label: "Departments",        color: "#6366f1", x: 555, y: 415, w: NW,  h: NH,
    desc: "Product categories (Plumbing, Electrical…). Used for filtering and reporting.",
    ai:   ["Which department burns the most stock?", "List all Electrical products"] },
  { id: "issue",      label: "Issue Materials",    color: "#3b82f6", x: 770, y: 208, w: NW,  h: NH,
    desc: "Hand materials to a contractor or job. Stock decrements immediately.",
    ai:   ["What was issued today?", "Show issues for contractor John"] },
  { id: "requests",   label: "Pending Requests",   color: "#f97316", x: 770, y: 358, w: NW,  h: NH,
    desc: "Contractor requests land here. You approve or deny before anything leaves.",
    ai:   ["How many requests are waiting?", "What did crew A request?"] },
  { id: "contractors",label: "Contractors",        color: "#84cc16", x: 900, y: 278, w: NW,  h: NH,
    desc: "Field workers. Full history of what each person received, per job.",
    ai:   ["What has John taken out?", "Which crew uses the most materials?"] },
  { id: "financials", label: "Financials",         color: "#e879f9", x: 840, y: 105, w: NW,  h: NH,
    desc: "High-level view: revenue, cost, profit/loss. Rolls up invoices and spend.",
    ai:   ["P&L this month", "Total outstanding balance", "Cost vs revenue"] },
];

const OP_EDGES = [
  { s: "vendors",    t: "po",          label: "order" },
  { s: "po",         t: "receive",     label: "fills" },
  { s: "po",         t: "invoices",    label: "billed as" },
  { s: "invoices",   t: "financials",  label: "tracked in" },
  { s: "receive",    t: "inventory",   label: "+stock" },
  { s: "depts",      t: "inventory",   label: "groups" },
  { s: "inventory",  t: "issue",       label: "pulled" },
  { s: "contractors",t: "requests",    label: "submit" },
  { s: "requests",   t: "issue",       label: "approved →" },
  { s: "issue",      t: "contractors", label: "issued to" },
];

function OperationalFlow({ selected, setSelected, w, h }) {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!w || !h || !svgRef.current) return;

    const sx = v => v / DW_OP * w;
    const sy = v => v / DH_OP * h;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.append("rect").attr("width", w).attr("height", h).attr("fill", BG);

    const defs = svg.append("defs");
    OP_NODES.forEach(n => addArrow(defs, `op-${n.id}`, n.color));

    // Scale node positions and dimensions
    const scaledNodes = OP_NODES.map(n => ({
      ...n,
      x: sx(n.x), y: sy(n.y),
      sw: sx(n.w ?? NW), sh: sy(n.h ?? NH),
    }));
    const nMap = Object.fromEntries(scaledNodes.map(n => [n.id, n]));

    const activeEdges = selected
      ? new Set(OP_EDGES.filter(e => e.s===selected||e.t===selected).flatMap(e=>[e.s,e.t]))
      : null;

    // Zone labels + dividers
    [[sx(85), "Procurement"], [sx(475), "Stock"], [sx(730), "Dispatch"]].forEach(([x, label]) => {
      svg.append("text").attr("x", x).attr("y", sy(36))
        .attr("fill", LINE).attr("font-size", 9).attr("font-weight", 700)
        .attr("font-family", "Inter, ui-sans-serif, sans-serif").attr("letter-spacing", 1.5)
        .text(label.toUpperCase());
    });
    [sx(372), sx(668)].forEach(x => {
      svg.append("line").attr("x1", x).attr("y1", sy(48)).attr("x2", x).attr("y2", h - sy(18))
        .attr("stroke", LINE).attr("stroke-width", 1).attr("stroke-dasharray", "3 5").attr("opacity", 0.35);
    });
    svg.append("text").attr("x", sx(430)).attr("y", sy(60))
      .attr("fill", LINE).attr("font-size", 8.5).attr("font-weight", 600).attr("text-anchor", "middle")
      .attr("font-family", "Inter, ui-sans-serif, sans-serif").attr("letter-spacing", 1.2)
      .text("FINANCE");

    // Edges
    OP_EDGES.forEach(edge => {
      const src = nMap[edge.s], tgt = nMap[edge.t];
      if (!src || !tgt) return;
      const sp = rectEdge(src.x, src.y, src.sw/2, src.sh/2, tgt.x, tgt.y, 2);
      const tp = rectEdge(tgt.x, tgt.y, tgt.sw/2, tgt.sh/2, src.x, src.y, 9);
      const isActive = activeEdges ? (activeEdges.has(edge.s) && activeEdges.has(edge.t)) : false;
      const color = isActive || !selected ? nMap[edge.s].color : LINE;
      const op    = selected ? (isActive ? 0.8 : 0.06) : 0.45;

      svg.append("path").attr("d", curvePath(sp.x,sp.y,tp.x,tp.y))
        .attr("fill","none").attr("stroke", color)
        .attr("stroke-width", isActive ? 2.2 : 1.3).attr("stroke-opacity", op)
        .attr("marker-end", `url(#op-${edge.t})`);

      if (!selected || isActive) {
        svg.append("text")
          .attr("x", (sp.x+tp.x)/2+2).attr("y", (sp.y+tp.y)/2 - 8)
          .attr("text-anchor","middle").attr("fill", isActive ? color : MUTED)
          .attr("font-size", 9).attr("font-weight", 500)
          .attr("font-family","ui-monospace, monospace").attr("opacity", isActive ? 0.9 : 0.55)
          .text(edge.label);
      }
    });

    // Nodes
    scaledNodes.forEach(n => {
      const isSel  = selected === n.id;
      const isConn = activeEdges?.has(n.id);
      const isDim  = selected && !isSel && !isConn;
      const nw = n.sw, nh = n.sh;

      const g = svg.append("g").attr("transform", `translate(${n.x-nw/2},${n.y-nh/2})`).style("cursor","pointer");

      if (isSel) g.append("rect").attr("x",-4).attr("y",-4).attr("width",nw+8).attr("height",nh+8)
        .attr("rx",13).attr("fill",n.color).attr("opacity",0.13);

      g.append("rect").attr("width",nw).attr("height",nh).attr("rx",9).attr("fill",SURF)
        .attr("stroke", isSel ? n.color : isDim ? CARD : LINE)
        .attr("stroke-width", isSel ? 2.5 : 1.2)
        .attr("opacity", isDim ? 0.2 : 1);

      g.append("rect").attr("x",0).attr("y",8).attr("width",3.5).attr("height",nh-16)
        .attr("rx",1.5).attr("fill",n.color).attr("opacity", isDim ? 0.15 : 1);

      g.append("text").attr("x",nw/2+2).attr("y",nh/2).attr("dy","0.35em")
        .attr("text-anchor","middle")
        .attr("fill", isSel ? n.color : isDim ? "#374151" : TEXT)
        .attr("font-size", n.id==="inventory" ? 13.5 : 12).attr("font-weight",600)
        .attr("font-family","Inter, ui-sans-serif, sans-serif").text(n.label);

      g.on("click", () => setSelected(prev => prev===n.id ? null : n.id));
    });

    svg.append("text").attr("x",16).attr("y",h-14)
      .attr("fill",LINE).attr("font-size",9).attr("font-family","Inter, ui-sans-serif, sans-serif")
      .text("click a section · edges highlight on selection");

  }, [selected, setSelected, w, h]);

  return <svg ref={svgRef} width={w} height={h} style={{ display: "block", position: "absolute", inset: 0 }} />;
}

// ════════════════════════════════════════════════════════════════════════════
// 3. AGENT ARCHITECTURE — hierarchical fixed layout
// ════════════════════════════════════════════════════════════════════════════
const DW_AG = 980, DH_AG = 490;
const AW = 152, AH = 60;
const DBW = 152, DBH = 44;

const AGENT_NODES = [
  { id:"ag-gen",  label:"General",   sub:"Dashboard",                          color:"#94a3b8", x:100, y:285,
    desc:"Cross-domain assistant. Active on the dashboard. Reaches all three data domains.",
    knows:["Stock status & low-stock alerts","Outstanding invoices","Pending requests","Stockout risk","Revenue vs spend"],
    eg:  ["What needs my attention today?","Summarize this week","Any stockout risks?"] },
  { id:"ag-inv",  label:"Inventory", sub:"Inventory · Vendors · Depts · Receive", color:"#10b981", x:280, y:285,
    desc:"Stock specialist. Handles all queries about products, receiving, vendors, and departments.",
    knows:["Live stock levels","Fast & slow-moving items","Reorder suggestions","Vendor–product links","Dept activity"],
    eg:  ["What's running low?","Slowest items this month?","When to reorder wood screws?"] },
  { id:"ag-ops",  label:"Ops",       sub:"Issue Materials · Requests · Contractors", color:"#06b6d4", x:460, y:285,
    desc:"Operations specialist. Handles material issues, contractor history, and pending requests.",
    knows:["Pending material requests","What each contractor received","Job-level material usage","Contractor patterns"],
    eg:  ["How many requests waiting?","What did John take last week?","Which job used most material?"] },
  { id:"ag-fin",  label:"Finance",   sub:"Financials · Invoices",              color:"#f43f5e", x:640, y:285,
    desc:"Finance specialist. Active on Financials and Invoices. P&L, balances, revenue.",
    knows:["Outstanding balances by vendor","Revenue & cost breakdown","Profit/loss summary","Top products by cost"],
    eg:  ["Overdue invoices?","Total outstanding?","P&L this month?"] },
  { id:"ag-ins",  label:"Insights",  sub:"Reports",                            color:"#8b5cf6", x:820, y:285,
    desc:"Analytics specialist. Surfaces trends, usage patterns, and stockout forecasts.",
    knows:["Consumption trends by department","Top products by volume","Items at stockout risk","Seasonal patterns"],
    eg:  ["Top dept by usage?","Items at risk this week?","Top 10 most-used products?"] },
];

const DB_NODES = [
  { id:"db-stock", label:"Stock DB",   detail:"Products · Departments · Vendors",  color:"#10b981", x:240, y:415 },
  { id:"db-ops",   label:"Ops DB",     detail:"Withdrawals · Requests · Contractors", color:"#06b6d4", x:460, y:415 },
  { id:"db-fin",   label:"Finance DB", detail:"Invoices · Purchase Orders",          color:"#f43f5e", x:680, y:415 },
];

const AGENT_DB_LINKS = [
  { a:"ag-gen", db:"db-stock"}, { a:"ag-gen", db:"db-ops"}, { a:"ag-gen", db:"db-fin"},
  { a:"ag-inv", db:"db-stock"},
  { a:"ag-ops", db:"db-ops"},
  { a:"ag-fin", db:"db-fin"},
  { a:"ag-ins", db:"db-stock"}, { a:"ag-ins", db:"db-ops"},
];

function AgentArchitecture({ selected, setSelected, w, h }) {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!w || !h || !svgRef.current) return;

    const sx = v => v / DW_AG * w;
    const sy = v => v / DH_AG * h;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.append("rect").attr("width",w).attr("height",h).attr("fill",BG);

    const defs = svg.append("defs");
    AGENT_NODES.forEach(a => addArrow(defs, `aw-a-${a.id}`, a.color));
    DB_NODES.forEach(d => addArrow(defs, `aw-d-${d.id}`, d.color));
    addArrow(defs,"aw-chat","#f59e0b");
    addArrow(defs,"aw-disp","#6b7280");

    const selAgent = selected ? AGENT_NODES.find(a=>a.id===selected) : null;
    const connectedDBs = selected
      ? new Set(AGENT_DB_LINKS.filter(l=>l.a===selected).map(l=>l.db))
      : null;

    // Scale nodes
    const scaledAgents = AGENT_NODES.map(a => ({ ...a, x: sx(a.x), y: sy(a.y), aw: sx(AW), ah: sy(AH) }));
    const scaledDBs    = DB_NODES.map(d => ({ ...d, x: sx(d.x), y: sy(d.y), dw: sx(DBW), dh: sy(DBH) }));

    // Row labels
    [["User", 60], ["Routing", 165], ["Agents", 285], ["Data", 415]].forEach(([label, y]) => {
      svg.append("text").attr("x",16).attr("y",sy(y)).attr("dy","0.35em")
        .attr("fill","#374151").attr("font-size",9).attr("font-weight",700)
        .attr("font-family","Inter, ui-sans-serif, sans-serif").attr("letter-spacing",1.2)
        .text(label.toUpperCase());
    });

    // Chat entry
    const chatX=sx(490), chatY=sy(60), chatW=sx(190), chatH=sy(46);
    const chatG = svg.append("g").attr("transform",`translate(${chatX-chatW/2},${chatY-chatH/2})`);
    chatG.append("rect").attr("width",chatW).attr("height",chatH).attr("rx",23)
      .attr("fill","#f59e0b").attr("fill-opacity",0.1).attr("stroke","#f59e0b").attr("stroke-width",1.8);
    chatG.append("text").attr("x",chatW/2).attr("y",chatH/2).attr("dy","0.35em")
      .attr("text-anchor","middle").attr("fill","#fcd34d")
      .attr("font-size",13).attr("font-weight",700).attr("font-family","Inter, ui-sans-serif, sans-serif")
      .text("Chat Assistant");

    // Dispatcher
    const dispX=sx(490), dispY=sy(165), dispW=sx(148), dispH=sy(36);
    svg.append("line").attr("x1",chatX).attr("y1",chatY+chatH/2)
      .attr("x2",dispX).attr("y2",dispY-dispH/2-4)
      .attr("stroke","#f59e0b").attr("stroke-width",1.5).attr("stroke-opacity",0.35).attr("stroke-dasharray","4 3")
      .attr("marker-end","url(#aw-disp)");
    const dispG = svg.append("g").attr("transform",`translate(${dispX-dispW/2},${dispY-dispH/2})`);
    dispG.append("rect").attr("width",dispW).attr("height",dispH).attr("rx",6)
      .attr("fill",SURF).attr("stroke",LINE).attr("stroke-width",1);
    dispG.append("text").attr("x",dispW/2).attr("y",dispH/2).attr("dy","0.35em")
      .attr("text-anchor","middle").attr("fill",MUTED)
      .attr("font-size",10).attr("font-weight",600).attr("font-family","ui-monospace, monospace")
      .text("assistant.py · dispatcher");

    // Dispatcher → Agent fan-out
    scaledAgents.forEach(agent => {
      const isDim = selected && selected!==agent.id;
      svg.append("path")
        .attr("d", curvePath(dispX, dispY+dispH/2, agent.x, agent.y-agent.ah/2-4))
        .attr("fill","none").attr("stroke", isDim ? LINE : agent.color)
        .attr("stroke-width", selected===agent.id ? 2.2 : 1.1)
        .attr("stroke-opacity", isDim ? 0.07 : 0.45)
        .attr("marker-end", `url(#aw-a-${agent.id})`);
    });

    // Agent → DB edges
    AGENT_DB_LINKS.forEach(({ a, db }) => {
      const agent = scaledAgents.find(n=>n.id===a);
      const zone  = scaledDBs.find(d=>d.id===db);
      if (!agent || !zone) return;
      const isSel = selected===a && connectedDBs?.has(db);
      const isDim = selected && !isSel;
      svg.append("path")
        .attr("d", curvePath(agent.x, agent.y+agent.ah/2, zone.x, zone.y-zone.dh/2-4))
        .attr("fill","none").attr("stroke", isSel ? agent.color : isDim ? LINE : zone.color)
        .attr("stroke-width", isSel ? 2.2 : 1)
        .attr("stroke-opacity", isDim ? 0.04 : isSel ? 0.7 : 0.28)
        .attr("stroke-dasharray", isSel ? null : "3 3")
        .attr("marker-end", `url(#aw-d-${db})`);
    });

    // Agent nodes
    scaledAgents.forEach(agent => {
      const isSel = selected===agent.id;
      const isDim = selected && !isSel;
      const aw = agent.aw, ah = agent.ah;

      const g = svg.append("g")
        .attr("transform",`translate(${agent.x-aw/2},${agent.y-ah/2})`).style("cursor","pointer");

      if (isSel) g.append("rect").attr("x",-5).attr("y",-5).attr("width",aw+10).attr("height",ah+10)
        .attr("rx",14).attr("fill",agent.color).attr("opacity",0.1);

      g.append("rect").attr("width",aw).attr("height",ah).attr("rx",10).attr("fill",SURF)
        .attr("stroke", isSel ? agent.color : isDim ? CARD : LINE)
        .attr("stroke-width", isSel ? 2.5 : 1).attr("opacity", isDim ? 0.2 : 1);

      g.append("rect").attr("x",0).attr("y",9).attr("width",3.5).attr("height",ah-18)
        .attr("rx",1.5).attr("fill",agent.color).attr("opacity", isDim ? 0.2 : 1);

      g.append("text").attr("x",aw/2+1).attr("y",ah/2-7).attr("dy","0.35em")
        .attr("text-anchor","middle")
        .attr("fill", isSel ? agent.color : isDim ? "#374151" : TEXT)
        .attr("font-size",12).attr("font-weight",700)
        .attr("font-family","Inter, ui-sans-serif, sans-serif")
        .text(agent.label+" Agent");
      g.append("text").attr("x",aw/2+1).attr("y",ah/2+9).attr("dy","0.35em")
        .attr("text-anchor","middle").attr("fill", isDim ? "#374151" : MUTED)
        .attr("font-size",8).attr("font-family","Inter, ui-sans-serif, sans-serif")
        .text(agent.sub.split("·")[0].trim() + (agent.sub.includes("·") ? " ···" : ""));

      g.on("click", () => setSelected(prev => prev===agent.id ? null : agent.id));
    });

    // DB nodes
    scaledDBs.forEach(zone => {
      const isDim = connectedDBs && !connectedDBs.has(zone.id);
      const dw = zone.dw, dh = zone.dh;
      const g = svg.append("g").attr("transform",`translate(${zone.x-dw/2},${zone.y-dh/2})`);
      g.append("rect").attr("width",dw).attr("height",dh).attr("rx",8)
        .attr("fill",zone.color).attr("fill-opacity", isDim ? 0.03 : 0.09)
        .attr("stroke",zone.color).attr("stroke-width",1.3).attr("opacity", isDim ? 0.18 : 1);
      g.append("text").attr("x",dw/2).attr("y",dh/2-6).attr("dy","0.35em")
        .attr("text-anchor","middle").attr("fill", isDim ? "#374151" : zone.color)
        .attr("font-size",11).attr("font-weight",700).attr("font-family","Inter, ui-sans-serif, sans-serif")
        .text(zone.label);
      g.append("text").attr("x",dw/2).attr("y",dh/2+9).attr("dy","0.35em")
        .attr("text-anchor","middle").attr("fill", isDim ? "#1f2937" : MUTED)
        .attr("font-size",8).attr("font-family","Inter, ui-sans-serif, sans-serif")
        .text(zone.detail);
    });

    svg.append("text").attr("x",w-16).attr("y",h-14).attr("text-anchor","end")
      .attr("fill",LINE).attr("font-size",9).attr("font-family","Inter, ui-sans-serif, sans-serif")
      .text("click agent to see capabilities and data reach");

  }, [selected, setSelected, w, h]);

  return <svg ref={svgRef} width={w} height={h} style={{ display: "block", position: "absolute", inset: 0 }} />;
}

// ─── Detail panel ────────────────────────────────────────────────────────────
const KG_MAP = Object.fromEntries(KG_NODES.map(n => [n.id, n]));
const OP_MAP = Object.fromEntries(OP_NODES.map(n => [n.id, n]));
const AG_MAP = Object.fromEntries(AGENT_NODES.map(n => [n.id, n]));

function Panel({ tab, sel, onClose }) {
  const empty = (Icon, msg) => (
    <div className="flex flex-col items-center justify-center h-40 gap-3 text-center px-4">
      <Icon className="w-6 h-6" style={{ color: LINE }} />
      <p className="text-xs leading-relaxed" style={{ color: MUTED }}>{msg}</p>
    </div>
  );

  if (tab === "domain") {
    const n = KG_MAP[sel];
    if (!n) return empty(Network, "Click any entity to see its schema and relationships");
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full shrink-0 mt-0.5" style={{ background: n.color }} />
            <h3 className="font-semibold text-sm" style={{ color: TEXT }}>{n.label}</h3>
          </div>
          <button onClick={onClose} className="shrink-0 p-0.5 rounded" style={{ color: MUTED }}>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: MUTED }}>{n.desc}</p>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: LINE }}>Schema fields</p>
          <code className="text-xs leading-relaxed font-mono block" style={{ color: MUTED }}>{n.props}</code>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: LINE }}>Linked to</p>
          <ul className="space-y-1">
            {KG_EDGES.filter(e=>e.s===n.id||e.t===n.id).map((e,i) => {
              const other = KG_MAP[e.s===n.id ? e.t : e.s];
              return (
                <li key={i} className="flex items-center gap-2 text-xs" style={{ color: MUTED }}>
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: other?.color }} />
                  <span style={{ color: other?.color }}>{other?.label}</span>
                  <span className="font-mono text-[10px]" style={{ color: LINE }}>·{e.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    );
  }

  if (tab === "flow") {
    const n = OP_MAP[sel];
    if (!n) return empty(GitBranch, "Click a section to see what happens there and what to ask the AI");
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full shrink-0 mt-0.5" style={{ background: n.color }} />
            <h3 className="font-semibold text-sm" style={{ color: TEXT }}>{n.label}</h3>
          </div>
          <button onClick={onClose} className="shrink-0 p-0.5 rounded" style={{ color: MUTED }}>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: MUTED }}>{n.desc}</p>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: LINE }}>
            <MessageSquare className="w-3 h-3" /> Ask the AI here
          </p>
          {n.ai.map((q,i) => (
            <p key={i} className="text-xs rounded-lg px-3 py-2 italic mb-1.5"
              style={{ background: n.color+"14", color: n.color }}>"{q}"</p>
          ))}
        </div>
      </div>
    );
  }

  if (tab === "agents") {
    const n = AG_MAP[sel];
    if (!n) return empty(Cpu, "Click an agent to see what it knows and how to talk to it");
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full shrink-0 mt-0.5" style={{ background: n.color }} />
            <div>
              <h3 className="font-semibold text-sm" style={{ color: TEXT }}>{n.label} Agent</h3>
              <p className="text-[10px] mt-0.5 font-mono" style={{ color: LINE }}>{n.sub}</p>
            </div>
          </div>
          <button onClick={onClose} className="shrink-0 p-0.5 rounded" style={{ color: MUTED }}>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: MUTED }}>{n.desc}</p>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: LINE }}>Knows about</p>
          {n.knows.map((k,i) => (
            <div key={i} className="flex items-start gap-2 text-xs mb-1.5" style={{ color: "#cbd5e1" }}>
              <ChevronRight className="w-3 h-3 mt-0.5 shrink-0" style={{ color: n.color }} />{k}
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: LINE }}>
            <MessageSquare className="w-3 h-3" /> Example questions
          </p>
          {n.eg.map((q,i) => (
            <p key={i} className="text-xs rounded-lg px-3 py-2 italic mb-1.5"
              style={{ background: n.color+"14", color: n.color }}>"{q}"</p>
          ))}
        </div>
      </div>
    );
  }
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE
// ════════════════════════════════════════════════════════════════════════════
const TABS = [
  { id:"domain",  label:"Domain Model",       Icon: Network,   desc:"Business entities and how they relate — the schema the AI reasons over" },
  { id:"flow",    label:"Operational Flow",   Icon: GitBranch, desc:"How goods, money, and requests move through the warehouse" },
  { id:"agents",  label:"Agent Architecture", Icon: Cpu,       desc:"How a user query gets routed to the right specialist and data" },
];

export default function Graphs() {
  const [tab, setTab] = useState("domain");
  const [domSel,  setDomSel]  = useState(null);
  const [flowSel, setFlowSel] = useState(null);
  const [agSel,   setAgSel]   = useState(null);

  const sel    = tab==="domain" ? domSel    : tab==="flow" ? flowSel : agSel;
  const setSel = tab==="domain" ? setDomSel : tab==="flow" ? setFlowSel : setAgSel;

  const [containerRef, { w, h }] = useSize();

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setSel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSel]);

  return (
    <div className="flex flex-col min-h-screen h-screen" style={{ background: "#080f1c", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "14px 24px 0", flexShrink: 0 }}>
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="flex items-center gap-1.5 text-sm font-medium transition-colors hover:opacity-90"
            style={{ color: MUTED }}
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </Link>
          <h1 style={{ color: TEXT, fontWeight: 600, fontSize: 18, letterSpacing: "-0.01em", margin: 0 }}>
            System Graphs
          </h1>
        </div>
        <p style={{ color: MUTED, fontSize: 12.5, marginTop: 3, marginBottom: 0 }}>
          {TABS.find(t=>t.id===tab)?.desc}
        </p>
      </div>

      {/* Tab bar */}
      <div style={{ padding: "10px 24px 12px", flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 2, background: CARD, border: `1px solid ${LINE}`, borderRadius: 12, padding: 4, width: "fit-content" }}>
          {TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                display: "flex", alignItems: "center", gap: 7,
                padding: "7px 16px", borderRadius: 8, border: "none", cursor: "pointer",
                fontSize: 13, fontWeight: 500, fontFamily: "Inter, ui-sans-serif, sans-serif",
                background: tab===id ? SURF : "transparent",
                color: tab===id ? TEXT : MUTED,
                transition: "all 0.15s",
              }}
            >
              <Icon style={{ width: 15, height: 15 }} />{label}
            </button>
          ))}
        </div>
      </div>

      {/* Graph area — fills remaining height, takes full width */}
      <div
        ref={containerRef}
        className="graph-viewport w-full flex-1 min-h-[50vh]"
        style={{ position: "relative", overflow: "hidden" }}
      >
        {w > 0 && h > 0 ? (
          <>
            {tab==="domain"  && <DomainModel       w={w} h={h} selected={domSel}  setSelected={setDomSel}  />}
            {tab==="flow"    && <OperationalFlow    w={w} h={h} selected={flowSel} setSelected={setFlowSel} />}
            {tab==="agents"  && <AgentArchitecture  w={w} h={h} selected={agSel}   setSelected={setAgSel}   />}
          </>
        ) : (
          <div className="flex items-center justify-center h-full" style={{ background: BG }}>
            <div className="flex flex-col items-center gap-3" style={{ color: MUTED }}>
              <Loader2 className="w-6 h-6 animate-spin" />
              <span className="text-sm font-medium">Preparing graph…</span>
            </div>
          </div>
        )}

        {/* Click-outside overlay when panel is open */}
        {/* Floating detail panel */}
        {sel && (
          <div
            role="dialog"
            aria-label="Node details"
            onClick={e => e.stopPropagation()}
            style={{
              position: "absolute", top: 16, right: 16,
              width: 272,
              maxHeight: "calc(100% - 32px)",
              background: CARD,
              border: `1px solid ${LINE}`,
              borderRadius: 16,
              padding: "16px",
              overflowY: "auto",
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              backdropFilter: "blur(4px)",
              zIndex: 10,
              animation: "graphPanelIn 0.2s ease-out",
            }}
          >
            <Panel tab={tab} sel={sel} onClose={() => setSel(null)} />
          </div>
        )}

        {/* Empty state hint when nothing is selected */}
        {!sel && w > 0 && (
          <div
            style={{
              position: "absolute", top: 16, right: 16,
              background: CARD + "cc",
              border: `1px solid ${LINE}`,
              borderRadius: 10,
              padding: "8px 14px",
              backdropFilter: "blur(4px)",
              zIndex: 5,
            }}
          >
            <p style={{ color: MUTED, fontSize: 11, margin: 0 }}>
              {tab==="domain"  ? "click entity to inspect" :
               tab==="flow"   ? "click section to explore" :
                                "click agent to inspect"}
            </p>
          </div>
        )}
      </div>

    </div>
  );
}
