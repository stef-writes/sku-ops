import { useState, useMemo } from "react";
import { useAuth } from "@/context/AuthContext";
import { Package, MapPin, ChevronDown, Send, Clock, FileText, X } from "lucide-react";
import { format } from "date-fns";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatCard } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { useWithdrawals } from "@/hooks/useWithdrawals";
import { useMaterialRequests } from "@/hooks/useMaterialRequests";
import { dateToISO, endOfDayISO } from "@/lib/utils";

const MyHistory = () => {
  const { user } = useAuth();
  const [dateRange, setDateRange] = useState({ from: null, to: null });
  const [paymentStatus, setPaymentStatus] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const params = useMemo(() => ({
    start_date: dateToISO(dateRange.from),
    end_date: endOfDayISO(dateRange.to),
    payment_status: paymentStatus || undefined,
  }), [dateRange, paymentStatus]);

  const { data: withdrawals = [], isLoading: wdLoading } = useWithdrawals(params);
  const { data: allRequests = [], isLoading: reqLoading } = useMaterialRequests();

  const requests = allRequests.filter?.((r) => r.status === "pending") || [];
  const totalSpent = withdrawals.reduce((sum, w) => sum + (w.total || 0), 0);
  const totalUninvoiced = withdrawals.filter((w) => !w.invoice_id).reduce((sum, w) => sum + (w.total || 0), 0);

  const hasFilters = dateRange.from || dateRange.to || paymentStatus;

  if (wdLoading || reqLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="my-history-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">My History</h1>
          <p className="text-muted-foreground mt-1 text-sm">{user?.name} · {user?.company || "Independent"}</p>
        </div>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Total Withdrawals" value={withdrawals.length} />
        <StatCard label="Total Value" value={`$${totalSpent.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} accent="emerald" />
        <StatCard label="Uninvoiced" value={`$${totalUninvoiced.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} accent="amber" />
      </div>

      {requests.length > 0 && (
        <div className="mb-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground mb-3">Pending Requests</p>
          <div className="space-y-2">
            {requests.map((r) => {
              const itemCount = (r.items || []).reduce((s, i) => s + (i.quantity || 0), 0);
              return (
                <div key={r.id} className="bg-card border border-border rounded-lg p-4 flex items-center justify-between shadow-sm" data-testid={`pending-request-${r.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-warning/10 flex items-center justify-center"><Send className="w-4 h-4 text-accent" /></div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Request submitted — pending pickup</p>
                      <p className="text-xs text-muted-foreground">{itemCount} items · {new Date(r.created_at).toLocaleDateString()}</p>
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
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">Withdrawals</p>
          <Select value={paymentStatus || "all"} onValueChange={(v) => setPaymentStatus(v === "all" ? "" : v)}>
            <SelectTrigger className="h-8 w-[140px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="unpaid">Uninvoiced</SelectItem>
              <SelectItem value="invoiced">Invoiced</SelectItem>
            </SelectContent>
          </Select>
          {hasFilters && (
            <button
              type="button"
              onClick={() => { setDateRange({ from: null, to: null }); setPaymentStatus(""); }}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <X className="w-3 h-3" /> Clear all
            </button>
          )}
        </div>

        {withdrawals.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-16 text-center shadow-sm">
            <Package className="w-10 h-10 mx-auto text-muted-foreground/60 mb-2" />
            <p className="text-sm text-muted-foreground">{hasFilters ? "No withdrawals match these filters" : "No withdrawals yet"}</p>
            {!hasFilters && <p className="text-xs text-muted-foreground mt-1">Submit a material request and staff will process it at pickup</p>}
          </div>
        ) : (
          <div className="space-y-2">
            {withdrawals.map((w) => (
              <div key={w.id} className="bg-card border border-border rounded-xl shadow-sm overflow-hidden" data-testid={`withdrawal-${w.id}`}>
                <button className="w-full p-4 flex items-center justify-between text-left hover:bg-muted/80 transition-colors" onClick={() => setExpandedId(expandedId === w.id ? null : w.id)}>
                  <div className="flex items-center gap-3 min-w-0">
                    <StatusIcon status={w.invoice_id ? "invoiced" : "uninvoiced"} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{w.id.slice(0, 8).toUpperCase()}</span>
                        <StatusBadge status={w.invoice_id ? "invoiced" : "uninvoiced"} />
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{format(new Date(w.created_at), "MMM d, yyyy")} · Job: {w.job_id || "—"} · {w.items?.length || 0} items</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="font-semibold text-foreground tabular-nums">${(w.total || 0).toFixed(2)}</span>
                    <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${expandedId === w.id ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {expandedId === w.id && (
                  <div className="border-t border-border/50 p-4 bg-muted/50">
                    {w.service_address && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3"><MapPin className="w-3.5 h-3.5" />{w.service_address}</div>
                    )}
                    <div className="space-y-1.5 mb-4">
                      {w.items?.map((item, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2.5 bg-card rounded-lg border border-border/50">
                          <div>
                            <p className="font-mono text-[10px] text-muted-foreground">{item.sku}</p>
                            <p className="text-sm text-foreground">{item.name}</p>
                          </div>
                          <div className="text-right text-sm">
                            <p className="text-muted-foreground tabular-nums">{item.quantity}{item.unit && item.unit !== "each" ? ` ${item.unit}` : ""} × ${(item.price || 0).toFixed(2)}</p>
                            <p className="font-semibold text-foreground tabular-nums">${(item.subtotal || 0).toFixed(2)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="border-t border-border/50 pt-3 space-y-1 text-sm">
                      <div className="flex justify-between text-muted-foreground"><span>Subtotal</span><span className="tabular-nums">${(w.subtotal || 0).toFixed(2)}</span></div>
                      <div className="flex justify-between text-muted-foreground"><span>Tax</span><span className="tabular-nums">${(w.tax || 0).toFixed(2)}</span></div>
                      <div className="flex justify-between font-semibold text-foreground pt-1"><span>Total</span><span className="tabular-nums">${(w.total || 0).toFixed(2)}</span></div>
                    </div>
                    {w.notes && <div className="mt-3 p-2.5 bg-warning/10 rounded-lg border border-warning/30 text-xs text-accent">{w.notes}</div>}
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

function StatusIcon({ status }) {
  const map = { invoiced: "bg-info/10 text-info", uninvoiced: "bg-warning/10 text-accent" };
  const Icon = status === "invoiced" ? FileText : Clock;
  return <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${map[status] || map.uninvoiced}`}><Icon className="w-4 h-4" /></div>;
}

export default MyHistory;
