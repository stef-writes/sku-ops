import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Package,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Clock,
  Loader2,
  Truck,
  BoxIcon,
} from "lucide-react";
import { API } from "@/lib/api";

const STATUS_BADGE = {
  ordered: "bg-slate-100 text-slate-600 border-slate-200",
  partial: "bg-blue-100 text-blue-700 border-blue-200",
  received: "bg-emerald-100 text-emerald-700 border-emerald-200",
};

const STATUS_LABEL = {
  ordered: "Ordered",
  partial: "Partial",
  received: "Received",
  // legacy alias
  pending: "Ordered",
};

export default function PurchaseOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [orderItems, setOrderItems] = useState({}); // po_id → items[]
  const [acting, setActing] = useState({}); // po_id → "delivery"|"receive"|false
  const [deliveredQtys, setDeliveredQtys] = useState({}); // item_id → qty
  const [selectedOrdered, setSelectedOrdered] = useState({}); // item_id → bool (for dock transition)
  const [selectedPending, setSelectedPending] = useState({}); // item_id → bool (for inventory)
  const [loadingItems, setLoadingItems] = useState({}); // po_id → bool

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/purchase-orders`);
      setOrders(res.data);
    } catch {
      toast.error("Failed to load purchase orders");
    } finally {
      setLoading(false);
    }
  };

  const loadItems = async (poId) => {
    setLoadingItems((prev) => ({ ...prev, [poId]: true }));
    try {
      const res = await axios.get(`${API}/purchase-orders/${poId}`);
      const items = res.data.items || [];
      setOrderItems((prev) => ({ ...prev, [poId]: items }));
      const qtys = {};
      const selO = {};
      const selP = {};
      for (const item of items) {
        if (item.status === "ordered") selO[item.id] = true;
        if (item.status === "pending") {
          qtys[item.id] = item.delivered_qty ?? item.ordered_qty ?? 1;
          selP[item.id] = true;
        }
      }
      setDeliveredQtys((prev) => ({ ...prev, ...qtys }));
      setSelectedOrdered((prev) => ({ ...prev, ...selO }));
      setSelectedPending((prev) => ({ ...prev, ...selP }));
    } catch {
      toast.error("Failed to load order items");
    } finally {
      setLoadingItems((prev) => ({ ...prev, [poId]: false }));
    }
  };

  const toggleExpand = async (po) => {
    if (expandedId === po.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(po.id);
    if (!orderItems[po.id]) {
      await loadItems(po.id);
    }
  };

  const markDeliveryReceived = async (poId) => {
    const items = orderItems[poId] || [];
    const itemIds = items
      .filter((i) => i.status === "ordered" && selectedOrdered[i.id])
      .map((i) => i.id);

    if (itemIds.length === 0) {
      toast.error("No items selected");
      return;
    }

    setActing((prev) => ({ ...prev, [poId]: "delivery" }));
    try {
      await axios.post(`${API}/purchase-orders/${poId}/delivery`, {
        item_ids: itemIds,
      });
      toast.success(`${itemIds.length} item(s) marked as received at dock`);
      await fetchOrders();
      delete orderItems[poId];
      setOrderItems({ ...orderItems });
      await loadItems(poId);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to mark delivery");
    } finally {
      setActing((prev) => ({ ...prev, [poId]: false }));
    }
  };

  const receiveIntoInventory = async (poId) => {
    const items = orderItems[poId] || [];
    const toReceive = items
      .filter((i) => i.status === "pending" && selectedPending[i.id])
      .map((i) => ({
        id: i.id,
        delivered_qty: parseInt(deliveredQtys[i.id] ?? i.ordered_qty ?? 1) || 1,
      }));

    if (toReceive.length === 0) {
      toast.error("No items selected");
      return;
    }

    setActing((prev) => ({ ...prev, [poId]: "receive" }));
    try {
      const res = await axios.post(`${API}/purchase-orders/${poId}/receive`, {
        items: toReceive,
      });
      const { received, matched, errors } = res.data;
      const total = received + matched;
      toast.success(
        `${total} item(s) added to inventory${errors > 0 ? ` (${errors} failed)` : ""}`
      );
      if (res.data.error_details?.length > 0) {
        res.data.error_details.forEach((e) =>
          toast.error(`${e.item || e.item_id}: ${e.error}`)
        );
      }
      await fetchOrders();
      delete orderItems[poId];
      setOrderItems({ ...orderItems });
      if (res.data.status !== "received") {
        await loadItems(poId);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to receive items");
    } finally {
      setActing((prev) => ({ ...prev, [poId]: false }));
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-3 text-slate-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading purchase orders…
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 mb-4">
          <Package className="w-4 h-4 text-slate-600" />
          <span className="text-sm font-medium text-slate-700">Inventory</span>
        </div>
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Purchase Orders
        </h1>
        <p className="text-slate-500 mt-1 text-sm">
          Track deliveries: ordered → at dock → received into inventory
        </p>
      </div>

      {orders.length === 0 ? (
        <div className="card-elevated p-16 text-center text-slate-400">
          <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <Truck className="w-7 h-7 text-slate-400" />
          </div>
          <p className="font-medium">No purchase orders yet</p>
          <p className="text-sm mt-1">
            Upload a document on the Receive Inventory page to create one
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {orders.map((po) => {
            const isOpen = expandedId === po.id;
            const items = orderItems[po.id] || [];
            const orderedItems = items.filter((i) => i.status === "ordered");
            const pendingItems = items.filter((i) => i.status === "pending");
            const isActingDelivery = acting[po.id] === "delivery";
            const isActingReceive = acting[po.id] === "receive";
            const selectedOrderedCount = orderedItems.filter((i) => selectedOrdered[i.id]).length;
            const selectedPendingCount = pendingItems.filter((i) => selectedPending[i.id]).length;

            return (
              <div key={po.id} className="card-elevated overflow-hidden">
                {/* PO header row */}
                <button
                  onClick={() => toggleExpand(po)}
                  className="w-full flex items-center gap-4 p-5 text-left hover:bg-slate-50/60 transition-colors"
                >
                  <span className="text-slate-400">
                    {isOpen ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-semibold text-slate-900">
                        {po.vendor_name}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full border font-medium ${STATUS_BADGE[po.status] || STATUS_BADGE.ordered}`}
                      >
                        {STATUS_LABEL[po.status] || po.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
                      <span>
                        {po.item_count} item{po.item_count !== 1 ? "s" : ""}
                      </span>
                      {po.ordered_count > 0 && (
                        <span className="flex items-center gap-1 text-slate-500">
                          <BoxIcon className="w-3.5 h-3.5" />
                          {po.ordered_count} ordered
                        </span>
                      )}
                      {po.pending_count > 0 && (
                        <span className="flex items-center gap-1 text-amber-600">
                          <Clock className="w-3.5 h-3.5" />
                          {po.pending_count} at dock
                        </span>
                      )}
                      {po.arrived_count > 0 && (
                        <span className="flex items-center gap-1 text-emerald-600">
                          <CheckCircle className="w-3.5 h-3.5" />
                          {po.arrived_count} received
                        </span>
                      )}
                      {po.document_date && <span>{po.document_date}</span>}
                      {po.total > 0 && (
                        <span>${Number(po.total).toFixed(2)}</span>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">
                    {new Date(po.created_at).toLocaleDateString()}
                  </span>
                </button>

                {/* Expanded items */}
                {isOpen && (
                  <div className="border-t border-slate-100 p-5 space-y-5">
                    {loadingItems[po.id] ? (
                      <div className="text-center text-slate-400 py-6">
                        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                        Loading items…
                      </div>
                    ) : (
                      <>
                        {/* Column headers */}
                        <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-3 items-center px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
                          <span className="w-5" />
                          <span>Product</span>
                          <span className="text-right w-20">Ordered</span>
                          <span className="text-right w-24">Deliver qty</span>
                          <span className="text-right w-16">Cost</span>
                          <span className="w-20 text-center">Status</span>
                        </div>

                        {/* --- ORDERED items --- */}
                        {orderedItems.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-medium text-slate-400 uppercase tracking-wide px-1">
                              Awaiting delivery
                            </p>
                            {orderedItems.map((item) => (
                              <div
                                key={item.id}
                                className={`grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-3 items-center p-3 rounded-xl border transition-all ${
                                  selectedOrdered[item.id]
                                    ? "border-slate-300 bg-slate-50/60"
                                    : "border-slate-200 bg-slate-50/30 opacity-60"
                                }`}
                              >
                                <div className="w-5">
                                  <button
                                    onClick={() =>
                                      setSelectedOrdered((prev) => ({
                                        ...prev,
                                        [item.id]: !prev[item.id],
                                      }))
                                    }
                                    className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                                      selectedOrdered[item.id]
                                        ? "bg-slate-500 border-slate-500"
                                        : "border-slate-300"
                                    }`}
                                  >
                                    {selectedOrdered[item.id] && (
                                      <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                      </svg>
                                    )}
                                  </button>
                                </div>
                                <ItemInfo item={item} />
                                <div className="w-20 text-right text-sm text-slate-600">{item.ordered_qty}</div>
                                <div className="w-24 text-right text-sm text-slate-400">—</div>
                                <div className="w-16 text-right text-sm text-slate-600">
                                  {item.cost > 0 ? `$${Number(item.cost).toFixed(2)}` : "—"}
                                </div>
                                <div className="w-20 flex justify-center">
                                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-slate-100 text-slate-500">
                                    Ordered
                                  </span>
                                </div>
                              </div>
                            ))}
                            <div className="flex items-center justify-between pt-1">
                              <p className="text-sm text-slate-500">
                                <strong>{selectedOrderedCount}</strong> of {orderedItems.length} selected
                              </p>
                              <Button
                                onClick={() => markDeliveryReceived(po.id)}
                                disabled={isActingDelivery || selectedOrderedCount === 0}
                                className="h-9 px-4 bg-slate-700 hover:bg-slate-800 text-white text-sm"
                              >
                                {isActingDelivery ? (
                                  <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Marking…
                                  </>
                                ) : (
                                  <>
                                    <Truck className="w-4 h-4 mr-2" />
                                    Mark Delivery Received at Dock
                                  </>
                                )}
                              </Button>
                            </div>
                          </div>
                        )}

                        {/* --- PENDING (at dock) items --- */}
                        {pendingItems.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-medium text-amber-600 uppercase tracking-wide px-1">
                              At dock — count & receive
                            </p>
                            {pendingItems.map((item) => (
                              <div
                                key={item.id}
                                className={`grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-3 items-center p-3 rounded-xl border transition-all ${
                                  selectedPending[item.id]
                                    ? "border-amber-200 bg-amber-50/40"
                                    : "border-slate-200 bg-slate-50/40 opacity-60"
                                }`}
                              >
                                <div className="w-5">
                                  <button
                                    onClick={() =>
                                      setSelectedPending((prev) => ({
                                        ...prev,
                                        [item.id]: !prev[item.id],
                                      }))
                                    }
                                    className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                                      selectedPending[item.id]
                                        ? "bg-amber-500 border-amber-500"
                                        : "border-slate-300"
                                    }`}
                                  >
                                    {selectedPending[item.id] && (
                                      <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                      </svg>
                                    )}
                                  </button>
                                </div>
                                <ItemInfo item={item} />
                                <div className="w-20 text-right text-sm text-slate-600">{item.ordered_qty}</div>
                                <div className="w-24">
                                  <Input
                                    type="number"
                                    min="0"
                                    value={deliveredQtys[item.id] ?? item.ordered_qty ?? 1}
                                    onChange={(e) =>
                                      setDeliveredQtys((prev) => ({
                                        ...prev,
                                        [item.id]: e.target.value,
                                      }))
                                    }
                                    className="input-field h-8 text-sm text-right"
                                  />
                                </div>
                                <div className="w-16 text-right text-sm text-slate-600">
                                  {item.cost > 0 ? `$${Number(item.cost).toFixed(2)}` : "—"}
                                </div>
                                <div className="w-20 flex justify-center">
                                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-amber-50 text-amber-600">
                                    At Dock
                                  </span>
                                </div>
                              </div>
                            ))}
                            <div className="flex items-center justify-between pt-1">
                              <p className="text-sm text-slate-500">
                                <strong>{selectedPendingCount}</strong> of {pendingItems.length} selected
                              </p>
                              <Button
                                onClick={() => receiveIntoInventory(po.id)}
                                disabled={isActingReceive || selectedPendingCount === 0}
                                className="btn-primary h-9 px-4"
                              >
                                {isActingReceive ? (
                                  <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Receiving…
                                  </>
                                ) : (
                                  <>
                                    <CheckCircle className="w-4 h-4 mr-2" />
                                    Receive into Inventory
                                  </>
                                )}
                              </Button>
                            </div>
                          </div>
                        )}

                        {/* --- ARRIVED items --- */}
                        {items.filter((i) => i.status === "arrived").length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-medium text-emerald-600 uppercase tracking-wide px-1">
                              Received into inventory
                            </p>
                            {items.filter((i) => i.status === "arrived").map((item) => (
                              <div
                                key={item.id}
                                className="grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-3 items-center p-3 rounded-xl border border-emerald-100 bg-emerald-50/30"
                              >
                                <div className="w-5">
                                  <CheckCircle className="w-5 h-5 text-emerald-500" />
                                </div>
                                <ItemInfo item={item} />
                                <div className="w-20 text-right text-sm text-slate-600">{item.ordered_qty}</div>
                                <div className="w-24 text-right text-sm text-slate-600">
                                  {item.delivered_qty ?? item.ordered_qty}
                                </div>
                                <div className="w-16 text-right text-sm text-slate-600">
                                  {item.cost > 0 ? `$${Number(item.cost).toFixed(2)}` : "—"}
                                </div>
                                <div className="w-20 flex justify-center">
                                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-600">
                                    Received
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {po.status === "received" && (
                          <div className="flex items-center gap-2 text-sm text-emerald-600 pt-2 border-t border-slate-100">
                            <CheckCircle className="w-4 h-4" />
                            All items received
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
    </div>
  );
}

function ItemInfo({ item }) {
  return (
    <div className="min-w-0">
      <p className="text-sm font-medium text-slate-800 truncate">{item.name}</p>
      <p className="text-xs text-slate-400 mt-0.5">
        {item.suggested_department}
        {item.base_unit && item.base_unit !== "each" && (
          <> · {item.pack_qty > 1 ? `${item.pack_qty} ` : ""}{item.base_unit}</>
        )}
        {item.original_sku && (
          <> · <span className="font-mono">{item.original_sku}</span></>
        )}
      </p>
    </div>
  );
}
