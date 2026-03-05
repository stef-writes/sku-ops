import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Package, MapPin, ChevronDown, Send, Clock, CheckCircle, FileText } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { useWithdrawals } from "@/hooks/useWithdrawals";
import { useMaterialRequests } from "@/hooks/useMaterialRequests";

const MyHistory = () => {
  const { user } = useAuth();
  const { data: withdrawals = [], isLoading: wdLoading } = useWithdrawals();
  const { data: allRequests = [], isLoading: reqLoading } = useMaterialRequests();
  const [expandedId, setExpandedId] = useState(null);

  const requests = allRequests.filter?.((r) => r.status === "pending") || [];
  const totalSpent = withdrawals.reduce((sum, w) => sum + (w.total || 0), 0);
  const totalUnpaid = withdrawals.filter((w) => w.payment_status === "unpaid").reduce((sum, w) => sum + (w.total || 0), 0);

  if (wdLoading || reqLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="my-history-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">My History</h1>
        <p className="text-slate-500 mt-1 text-sm">{user?.name} · {user?.company || "Independent"}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <SummaryCard label="Total Withdrawals" value={withdrawals.length} />
        <SummaryCard label="Total Value" value={`$${totalSpent.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} accent="emerald" />
        <SummaryCard label="Unpaid Balance" value={`$${totalUnpaid.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} accent="amber" />
      </div>

      {requests.length > 0 && (
        <div className="mb-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">Pending Requests</p>
          <div className="space-y-2">
            {requests.map((r) => {
              const itemCount = (r.items || []).reduce((s, i) => s + (i.quantity || 0), 0);
              return (
                <div key={r.id} className="bg-white border border-slate-200 rounded-lg p-4 flex items-center justify-between shadow-sm" data-testid={`pending-request-${r.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center"><Send className="w-4 h-4 text-amber-500" /></div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">Request submitted — pending pickup</p>
                      <p className="text-xs text-slate-400">{itemCount} items · {new Date(r.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <StatusBadge status="pending" />
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div data-testid="withdrawals-list">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">Withdrawals</p>
        {withdrawals.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-16 text-center shadow-sm">
            <Package className="w-10 h-10 mx-auto text-slate-300 mb-2" />
            <p className="text-sm text-slate-500">No withdrawals yet</p>
            <p className="text-xs text-slate-400 mt-1">Submit a material request and staff will process it at pickup</p>
          </div>
        ) : (
          <div className="space-y-2">
            {withdrawals.map((w) => (
              <div key={w.id} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden" data-testid={`withdrawal-${w.id}`}>
                <button className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50/80 transition-colors" onClick={() => setExpandedId(expandedId === w.id ? null : w.id)}>
                  <div className="flex items-center gap-3 min-w-0">
                    <StatusIcon status={w.payment_status} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-slate-400">{w.id.slice(0, 8).toUpperCase()}</span>
                        <StatusBadge status={w.payment_status} />
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">{format(new Date(w.created_at), "MMM d, yyyy")} · Job: {w.job_id || "—"} · {w.items?.length || 0} items</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="font-semibold text-slate-900 tabular-nums">${(w.total || 0).toFixed(2)}</span>
                    <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${expandedId === w.id ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {expandedId === w.id && (
                  <div className="border-t border-slate-100 p-4 bg-slate-50/50">
                    {w.service_address && (
                      <div className="flex items-center gap-2 text-xs text-slate-500 mb-3"><MapPin className="w-3.5 h-3.5" />{w.service_address}</div>
                    )}
                    <div className="space-y-1.5 mb-4">
                      {w.items?.map((item, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2.5 bg-white rounded-lg border border-slate-100">
                          <div>
                            <p className="font-mono text-[10px] text-slate-400">{item.sku}</p>
                            <p className="text-sm text-slate-800">{item.name}</p>
                          </div>
                          <div className="text-right text-sm">
                            <p className="text-slate-500 tabular-nums">{item.quantity}{item.unit && item.unit !== "each" ? ` ${item.unit}` : ""} × ${(item.price || 0).toFixed(2)}</p>
                            <p className="font-semibold text-slate-900 tabular-nums">${(item.subtotal || 0).toFixed(2)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="border-t border-slate-100 pt-3 space-y-1 text-sm">
                      <div className="flex justify-between text-slate-500"><span>Subtotal</span><span className="tabular-nums">${(w.subtotal || 0).toFixed(2)}</span></div>
                      <div className="flex justify-between text-slate-500"><span>Tax</span><span className="tabular-nums">${(w.tax || 0).toFixed(2)}</span></div>
                      <div className="flex justify-between font-semibold text-slate-900 pt-1"><span>Total</span><span className="tabular-nums">${(w.total || 0).toFixed(2)}</span></div>
                    </div>
                    {w.notes && <div className="mt-3 p-2.5 bg-amber-50/80 rounded-lg border border-amber-100 text-xs text-amber-800">{w.notes}</div>}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

function SummaryCard({ label, value, accent = "slate" }) {
  const bar = { emerald: "bg-emerald-400", amber: "bg-amber-400", slate: "bg-slate-200" }[accent] || "bg-slate-200";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${bar}`} />
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">{label}</p>
      <p className="text-2xl font-bold text-slate-900 tabular-nums leading-none">{value}</p>
    </div>
  );
}

function StatusIcon({ status }) {
  const map = { paid: "bg-emerald-50 text-emerald-500", invoiced: "bg-blue-50 text-blue-500", unpaid: "bg-amber-50 text-amber-500" };
  const Icon = status === "paid" ? CheckCircle : status === "invoiced" ? FileText : Clock;
  return <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${map[status] || map.unpaid}`}><Icon className="w-4 h-4" /></div>;
}

export default MyHistory;
