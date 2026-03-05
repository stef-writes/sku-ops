import { useState, useMemo } from "react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ChevronDown, ChevronRight, CheckCircle, Clock, Loader2, Truck, BoxIcon, Filter, X } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { ReceiveReviewModal } from "@/components/ReceiveReviewModal";
import { usePurchaseOrders, usePOItems, useMarkDelivery, useReceivePO } from "@/hooks/usePurchaseOrders";
import { useDepartments } from "@/hooks/useDepartments";
import api from "@/lib/api-client";
import { getErrorMessage } from "@/lib/api-client";

const PO_STATUSES = [
  { value: "", label: "All statuses" },
  { value: "ordered", label: "Ordered" },
  { value: "partial", label: "Partial" },
  { value: "received", label: "Received" },
];

export default function PurchaseOrders() {
  const [statusFilter, setStatusFilter] = useState("");

  const params = useMemo(() => ({
    status: statusFilter || undefined,
  }), [statusFilter]);

  const { data: orders = [], isLoading } = usePurchaseOrders(params);
  const { data: departments = [] } = useDepartments();
  const markDelivery = useMarkDelivery();
  const receivePO = useReceivePO();

  const [expandedId, setExpandedId] = useState(null);
  const [orderItems, setOrderItems] = useState({});
  const [deliveredQtys, setDeliveredQtys] = useState({});
  const [selectedOrdered, setSelectedOrdered] = useState({});
  const [selectedPending, setSelectedPending] = useState({});
  const [loadingItems, setLoadingItems] = useState({});
  const [acting, setActing] = useState({});
  const [reviewModal, setReviewModal] = useState({ open: false, poId: null, items: [] });

  const loadItems = async (poId) => {
    setLoadingItems((p) => ({ ...p, [poId]: true }));
    try {
      const res = await api.purchaseOrders.get(poId);
      const items = res.items || [];
      setOrderItems((p) => ({ ...p, [poId]: items }));
      const qtys = {}; const selO = {}; const selP = {};
      for (const item of items) {
        if (item.status === "ordered") selO[item.id] = true;
        if (item.status === "pending") { qtys[item.id] = item.delivered_qty ?? item.ordered_qty ?? 1; selP[item.id] = true; }
      }
      setDeliveredQtys((p) => ({ ...p, ...qtys }));
      setSelectedOrdered((p) => ({ ...p, ...selO }));
      setSelectedPending((p) => ({ ...p, ...selP }));
    } catch { toast.error("Failed to load items"); }
    finally { setLoadingItems((p) => ({ ...p, [poId]: false })); }
  };

  const toggleExpand = async (po) => {
    if (expandedId === po.id) { setExpandedId(null); return; }
    setExpandedId(po.id);
    if (!orderItems[po.id]) await loadItems(po.id);
  };

  const markDeliveryReceived = async (poId) => {
    const items = orderItems[poId] || [];
    const itemIds = items.filter((i) => i.status === "ordered" && selectedOrdered[i.id]).map((i) => i.id);
    if (itemIds.length === 0) { toast.error("No items selected"); return; }
    setActing((p) => ({ ...p, [poId]: "delivery" }));
    try {
      await markDelivery.mutateAsync({ id: poId, data: { item_ids: itemIds } });
      toast.success(`${itemIds.length} item(s) marked as received at dock`);
      delete orderItems[poId]; setOrderItems({ ...orderItems });
      await loadItems(poId);
    } catch (e) { toast.error(getErrorMessage(e)); }
    finally { setActing((p) => ({ ...p, [poId]: false })); }
  };

  const openReceiveReview = (poId) => {
    const items = orderItems[poId] || [];
    const pending = items.filter((i) => i.status === "pending" && selectedPending[i.id]);
    if (pending.length === 0) { toast.error("No items selected"); return; }
    const withQtys = pending.map((i) => ({
      ...i,
      _delivered_qty: deliveredQtys[i.id] ?? i.delivered_qty ?? i.ordered_qty ?? 1,
    }));
    setReviewModal({ open: true, poId, items: withQtys });
  };

  const confirmReceive = async (payload) => {
    const poId = reviewModal.poId;
    setActing((p) => ({ ...p, [poId]: "receive" }));
    try {
      const res = await receivePO.mutateAsync({ id: poId, data: { items: payload } });
      const total = (res.received || 0) + (res.matched || 0);
      toast.success(`${total} item(s) added to inventory${res.errors > 0 ? ` (${res.errors} failed)` : ""}`);
      res.error_details?.forEach((e) => toast.error(`${e.item || e.item_id}: ${e.error}`));
      setReviewModal({ open: false, poId: null, items: [] });
      delete orderItems[poId]; setOrderItems({ ...orderItems });
      if (res.status !== "received") await loadItems(poId);
    } catch (e) { toast.error(getErrorMessage(e)); }
    finally { setActing((p) => ({ ...p, [poId]: false })); }
  };

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="purchase-orders-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Purchase Orders</h1>
        <p className="text-slate-500 mt-1 text-sm">Track deliveries: ordered → at dock → received into inventory</p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Filter className="w-3.5 h-3.5" />
          <span className="text-xs font-medium uppercase tracking-wide">Filter</span>
        </div>
        <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
          <SelectTrigger className="h-8 w-[140px]"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            {PO_STATUSES.map((s) => (
              <SelectItem key={s.value || "all"} value={s.value || "all"}>{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {statusFilter && (
          <button
            type="button"
            onClick={() => setStatusFilter("")}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
          >
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      {orders.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-16 text-center shadow-sm">
          <Truck className="w-10 h-10 mx-auto text-slate-300 mb-3" />
          <p className="font-medium text-slate-600">No purchase orders yet</p>
          <p className="text-sm text-slate-400 mt-1">Upload a document on the Receive page to create one</p>
        </div>
      ) : (
        <div className="space-y-2">
          {orders.map((po) => {
            const isOpen = expandedId === po.id;
            const items = orderItems[po.id] || [];
            const orderedItems = items.filter((i) => i.status === "ordered");
            const pendingItems = items.filter((i) => i.status === "pending");
            const arrivedItems = items.filter((i) => i.status === "arrived");
            const isActingDelivery = acting[po.id] === "delivery";
            const isActingReceive = acting[po.id] === "receive";
            const selectedOrderedCount = orderedItems.filter((i) => selectedOrdered[i.id]).length;
            const selectedPendingCount = pendingItems.filter((i) => selectedPending[i.id]).length;
            return (
              <div key={po.id} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                <button onClick={() => toggleExpand(po)} className="w-full flex items-center gap-4 p-5 text-left hover:bg-slate-50/60 transition-colors">
                  <span className="text-slate-400">{isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-slate-900">{po.vendor_name}</span>
                      <StatusBadge status={po.status} />
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                      <span>{po.item_count} item{po.item_count !== 1 ? "s" : ""}</span>
                      {po.ordered_count > 0 && <span className="flex items-center gap-1"><BoxIcon className="w-3 h-3" />{po.ordered_count} ordered</span>}
                      {po.pending_count > 0 && <span className="flex items-center gap-1 text-amber-600"><Clock className="w-3 h-3" />{po.pending_count} at dock</span>}
                      {po.arrived_count > 0 && <span className="flex items-center gap-1 text-emerald-600"><CheckCircle className="w-3 h-3" />{po.arrived_count} received</span>}
                      {po.total > 0 && <span className="tabular-nums">${Number(po.total).toFixed(2)}</span>}
                    </div>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">{new Date(po.created_at).toLocaleDateString()}</span>
                </button>
                {isOpen && (
                  <div className="border-t border-slate-100 p-5 space-y-5">
                    {loadingItems[po.id] ? (
                      <div className="text-center text-slate-400 py-6"><Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />Loading items…</div>
                    ) : (
                      <>
                        {orderedItems.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Awaiting delivery</p>
                            {orderedItems.map((item) => (
                              <ItemRow key={item.id} item={item} selected={selectedOrdered[item.id]} onToggle={() => setSelectedOrdered((p) => ({ ...p, [item.id]: !p[item.id] }))} color="slate" />
                            ))}
                            <div className="flex items-center justify-between pt-1">
                              <p className="text-xs text-slate-500"><strong>{selectedOrderedCount}</strong> of {orderedItems.length} selected</p>
                              <Button onClick={() => markDeliveryReceived(po.id)} disabled={isActingDelivery || selectedOrderedCount === 0} size="sm" className="gap-1">
                                {isActingDelivery ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Marking…</> : <><Truck className="w-3.5 h-3.5" />Mark Delivery at Dock</>}
                              </Button>
                            </div>
                          </div>
                        )}
                        {pendingItems.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-500">At dock — count & receive</p>
                            {pendingItems.map((item) => (
                              <ItemRow key={item.id} item={item} selected={selectedPending[item.id]} onToggle={() => setSelectedPending((p) => ({ ...p, [item.id]: !p[item.id] }))} color="amber" showQtyInput deliveredQty={deliveredQtys[item.id] ?? item.ordered_qty ?? 1} onQtyChange={(v) => setDeliveredQtys((p) => ({ ...p, [item.id]: v }))} />
                            ))}
                            <div className="flex items-center justify-between pt-1">
                              <p className="text-xs text-slate-500"><strong>{selectedPendingCount}</strong> of {pendingItems.length} selected</p>
                              <Button onClick={() => openReceiveReview(po.id)} disabled={isActingReceive || selectedPendingCount === 0} size="sm" className="gap-1">
                                {isActingReceive ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Receiving…</> : <><CheckCircle className="w-3.5 h-3.5" />Receive into Inventory</>}
                              </Button>
                            </div>
                          </div>
                        )}
                        {arrivedItems.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-500">Received into inventory</p>
                            {arrivedItems.map((item) => (
                              <div key={item.id} className="flex items-center gap-3 p-3 rounded-lg border border-emerald-100 bg-emerald-50/30">
                                <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                                <ItemInfo item={item} />
                                <span className="text-xs text-slate-500 tabular-nums shrink-0">ordered {item.ordered_qty}</span>
                                <span className="text-xs text-slate-600 tabular-nums shrink-0">delivered {item.delivered_qty ?? item.ordered_qty}</span>
                                {item.cost > 0 && <span className="text-xs text-slate-600 tabular-nums shrink-0">${Number(item.cost).toFixed(2)}</span>}
                              </div>
                            ))}
                          </div>
                        )}
                        {po.status === "received" && (
                          <div className="flex items-center gap-2 text-xs text-emerald-600 pt-2 border-t border-slate-100">
                            <CheckCircle className="w-3.5 h-3.5" />All items received
                            {po.received_by_name && ` by ${po.received_by_name}`}
                            {po.received_at && ` on ${new Date(po.received_at).toLocaleDateString()}`}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <ReceiveReviewModal
        open={reviewModal.open}
        onOpenChange={(v) => !v && setReviewModal({ open: false, poId: null, items: [] })}
        items={reviewModal.items}
        departments={departments}
        onConfirm={confirmReceive}
        isSubmitting={acting[reviewModal.poId] === "receive"}
      />
    </div>
  );
}

function ItemRow({ item, selected, onToggle, color, showQtyInput, deliveredQty, onQtyChange }) {
  const borderCls = selected ? (color === "amber" ? "border-amber-200 bg-amber-50/40" : "border-slate-300 bg-slate-50/60") : "border-slate-200 bg-slate-50/30 opacity-60";
  const checkCls = selected ? (color === "amber" ? "bg-amber-500 border-amber-500" : "bg-slate-500 border-slate-500") : "border-slate-300";
  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${borderCls}`}>
      <button onClick={onToggle} className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors shrink-0 ${checkCls}`}>
        {selected && <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>}
      </button>
      <ItemInfo item={item} />
      <span className="text-xs text-slate-500 tabular-nums shrink-0 w-16 text-right">{item.ordered_qty}</span>
      {showQtyInput ? (
        <Input type="number" min="0" step="any" value={deliveredQty} onChange={(e) => onQtyChange?.(e.target.value)} className="h-8 text-sm text-right w-20" />
      ) : (
        <span className="text-xs text-slate-400 w-20 text-right">—</span>
      )}
      <span className="text-xs text-slate-600 tabular-nums shrink-0 w-16 text-right">{item.cost > 0 ? `$${Number(item.cost).toFixed(2)}` : "—"}</span>
    </div>
  );
}

function ItemInfo({ item }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="text-sm font-medium text-slate-800 truncate">{item.name}</p>
      <p className="text-[10px] text-slate-400 mt-0.5">
        {item.suggested_department}
        {item.base_unit && item.base_unit !== "each" && <> · {item.pack_qty > 1 ? `${item.pack_qty} ` : ""}{item.base_unit}</>}
        {item.original_sku && <> · <span className="font-mono">{item.original_sku}</span></>}
      </p>
    </div>
  );
}
