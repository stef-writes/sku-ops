import { useState, useMemo } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { DollarSign, CheckCircle, Download, Calendar as CalendarIcon, FileText, HardHat, Building2, ArrowRight } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { CreateInvoiceModal } from "../components/CreateInvoiceModal";
import { useFinancialSummary } from "@/hooks/useFinancials";
import { useWithdrawals, useMarkPaid, useBulkMarkPaid } from "@/hooks/useWithdrawals";
import api from "@/lib/api-client";
import { valueFormatter } from "@/lib/chartConfig";

const Financials = () => {
  const [statusFilter, setStatusFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [dateRange, setDateRange] = useState({ from: null, to: null });
  const [selectedIds, setSelectedIds] = useState([]);
  const [createInvoiceModalOpen, setCreateInvoiceModalOpen] = useState(false);

  const params = useMemo(() => ({
    payment_status: statusFilter || undefined,
    billing_entity: entityFilter || undefined,
    start_date: dateRange.from?.toISOString(),
    end_date: dateRange.to?.toISOString(),
  }), [statusFilter, entityFilter, dateRange]);

  const { data: summary, isLoading: summaryLoading } = useFinancialSummary(params);
  const { data: withdrawals = [], isLoading: wdLoading } = useWithdrawals(params);
  const markPaid = useMarkPaid();
  const bulkMarkPaid = useBulkMarkPaid();

  const handleMarkPaid = async (id) => {
    try {
      await markPaid.mutateAsync({ id });
      toast.success("Marked as paid");
    } catch { toast.error("Failed to mark as paid"); }
  };

  const handleBulkMarkPaid = async () => {
    if (selectedIds.length === 0) return;
    try {
      await bulkMarkPaid.mutateAsync(selectedIds);
      toast.success(`Marked ${selectedIds.length} as paid`);
      setSelectedIds([]);
    } catch { toast.error("Failed to mark as paid"); }
  };

  const handleExport = async () => {
    try {
      const blob = await api.financials.export(params);
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `financials_${format(new Date(), "yyyyMMdd")}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success("Export downloaded");
    } catch { toast.error("Failed to export"); }
  };

  const toggleSelect = (id) => setSelectedIds((prev) => prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]);
  const selectAllUnpaid = () => setSelectedIds(withdrawals.filter((w) => w.payment_status === "unpaid" && !w.invoice_id).map((w) => w.id));
  const selectedUnpaidIds = selectedIds.filter((id) => { const w = withdrawals.find((x) => x.id === id); return w?.payment_status === "unpaid" && !w?.invoice_id; });
  const billingEntities = [...new Set(withdrawals.map((w) => w.billing_entity).filter(Boolean))];

  const paymentBreakdown = useMemo(() => {
    const paid = summary?.total_paid || 0;
    const unpaid = summary?.total_unpaid || 0;
    const invoiced = summary?.total_invoiced || 0;
    const total = paid + unpaid + invoiced || 1;
    return [
      { label: "Paid", value: paid, pct: (paid / total * 100).toFixed(0), color: "bg-emerald-400" },
      { label: "Invoiced", value: invoiced, pct: (invoiced / total * 100).toFixed(0), color: "bg-blue-400" },
      { label: "Unpaid", value: unpaid, pct: (unpaid / total * 100).toFixed(0), color: "bg-orange-400" },
    ].filter((d) => d.value > 0);
  }, [summary]);

  if (summaryLoading && wdLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="financials-page">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Financials</h1>
          <p className="text-slate-500 mt-1 text-sm">Payments, invoicing, and exports</p>
        </div>
        <div className="flex gap-2">
          <Link to="/invoices"><Button variant="outline" size="sm" className="gap-2"><FileText className="w-4 h-4" />Invoices</Button></Link>
          <Button variant="outline" size="sm" onClick={handleExport} className="gap-2" data-testid="export-btn"><Download className="w-4 h-4" />Export CSV</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6" data-testid="summary-cards">
        <MetricCard label="Unpaid" value={valueFormatter(summary?.total_unpaid || 0)} accent="rose" />
        <MetricCard label="Paid" value={valueFormatter(summary?.total_paid || 0)} accent="emerald" />
        <MetricCard label="Total Revenue" value={valueFormatter(summary?.total_revenue || 0)} />
        <MetricCard label="Gross Margin" value={valueFormatter(summary?.gross_margin || 0)} accent="violet" />
      </div>

      {paymentBreakdown.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">Payment Status</p>
          <div className="flex h-2.5 rounded-full overflow-hidden gap-px mb-3">
            {paymentBreakdown.map((d) => <div key={d.label} className={`${d.color} transition-all duration-500`} style={{ width: `${d.pct}%` }} title={`${d.label}: ${valueFormatter(d.value)}`} />)}
          </div>
          <div className="flex flex-wrap gap-4">
            {paymentBreakdown.map((d) => (
              <div key={d.label} className="flex items-center gap-1.5 text-xs">
                <div className={`w-2 h-2 rounded-full ${d.color}`} />
                <span className="text-slate-500">{d.label}</span>
                <span className="font-semibold text-slate-700 tabular-nums">{valueFormatter(d.value)}</span>
                <span className="text-slate-400">({d.pct}%)</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary?.by_contractor?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">Top Contractors by Spend</p>
          <div className="space-y-2">
            {summary.by_contractor.sort((a, b) => (b.total || 0) - (a.total || 0)).slice(0, 8).map((c, i) => {
              const max = summary.by_contractor[0]?.total || 1;
              return (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-[10px] font-bold text-slate-300 w-4 tabular-nums">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-700 truncate">{c.name || c.company || "Unknown"}</p>
                    <div className="h-1 bg-slate-100 rounded-full overflow-hidden mt-1"><div className="h-full bg-amber-400 rounded-full" style={{ width: `${((c.total || 0) / max * 100).toFixed(1)}%` }} /></div>
                  </div>
                  <span className="text-sm font-semibold text-slate-900 tabular-nums shrink-0">{valueFormatter(c.total || 0)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {summary?.by_billing_entity && Object.keys(summary.by_billing_entity).length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">By Billing Entity</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(summary.by_billing_entity).map(([entity, data]) => (
              <div key={entity} className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div className="flex items-center gap-2 mb-2"><Building2 className="w-3.5 h-3.5 text-slate-400" /><span className="text-sm font-semibold text-slate-800">{entity}</span></div>
                <div className="space-y-0.5 text-xs">
                  <div className="flex justify-between"><span className="text-slate-500">Total</span><span className="font-mono tabular-nums">${data.total.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-red-500">Unpaid</span><span className="font-mono tabular-nums text-red-600">${data.unpaid.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-slate-400">Txns</span><span className="font-mono tabular-nums">{data.count}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm mb-4" data-testid="filters">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Filter</span>
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[140px] h-9"><SelectValue placeholder="All Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="unpaid">Unpaid</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
              <SelectItem value="invoiced">Invoiced</SelectItem>
            </SelectContent>
          </Select>
          <Select value={entityFilter || "all"} onValueChange={(v) => setEntityFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[160px] h-9"><SelectValue placeholder="All Entities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              {billingEntities.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2"><CalendarIcon className="w-4 h-4" />{dateRange.from ? (dateRange.to ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}` : format(dateRange.from, "MMM d, yyyy")) : "Date range"}</Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start"><Calendar mode="range" selected={dateRange} onSelect={(r) => setDateRange(r || { from: null, to: null })} numberOfMonths={2} /></PopoverContent>
          </Popover>
          {(statusFilter || entityFilter || dateRange.from) && (
            <button onClick={() => { setStatusFilter(""); setEntityFilter(""); setDateRange({ from: null, to: null }); }} className="text-xs text-slate-400 hover:text-slate-600">Clear</button>
          )}
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-orange-700">{selectedIds.length} selected</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds([])}>Clear</Button>
            {selectedUnpaidIds.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setCreateInvoiceModalOpen(true)} className="gap-1"><FileText className="w-3.5 h-3.5" />Invoice ({selectedUnpaidIds.length})</Button>
            )}
            <Button size="sm" onClick={handleBulkMarkPaid} data-testid="bulk-mark-paid-btn" className="gap-1"><CheckCircle className="w-3.5 h-3.5" />Mark Paid</Button>
          </div>
        </div>
      )}

      <CreateInvoiceModal open={createInvoiceModalOpen} onOpenChange={setCreateInvoiceModalOpen} onCreated={() => { setSelectedIds([]); }} preselectedIds={selectedUnpaidIds} />

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden" data-testid="transactions-table">
        <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Transactions ({withdrawals.length})</p>
          <button onClick={selectAllUnpaid} className="text-xs text-orange-500 hover:text-orange-600 font-medium">Select All Unpaid</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-100">
              <th className="w-10 px-3 py-2.5" /><th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Date</th><th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Contractor</th><th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Job</th><th className="text-right text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Total</th><th className="text-right text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Cost</th><th className="text-right text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Margin</th><th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Status</th><th className="w-24 px-3 py-2.5" />
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {withdrawals.length === 0 ? (
                <tr><td colSpan="9" className="text-center py-12 text-slate-400 text-sm">No transactions found</td></tr>
              ) : withdrawals.map((w) => (
                <tr key={w.id} className="hover:bg-slate-50/60 transition-colors" data-testid={`transaction-row-${w.id}`}>
                  <td className="px-3 py-2.5"><input type="checkbox" checked={selectedIds.includes(w.id)} onChange={() => toggleSelect(w.id)} disabled={!!w.invoice_id} className="w-4 h-4 rounded border-slate-300 accent-orange-500 disabled:opacity-30" /></td>
                  <td className="px-3 py-2.5 font-mono text-xs text-slate-500">{new Date(w.created_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2.5"><div className="flex items-center gap-2"><HardHat className="w-3.5 h-3.5 text-slate-400" /><div><p className="font-medium text-slate-800">{w.contractor_name}</p><p className="text-[10px] text-slate-400">{w.contractor_company}</p></div></div></td>
                  <td className="px-3 py-2.5 font-mono text-xs">{w.job_id}</td>
                  <td className="px-3 py-2.5 text-right font-semibold tabular-nums">${(w.total || 0).toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-500 tabular-nums">${(w.cost_total || 0).toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right text-emerald-600 tabular-nums">${((w.total || 0) - (w.cost_total || 0)).toFixed(2)}</td>
                  <td className="px-3 py-2.5">
                    {w.payment_status === "invoiced" && w.invoice_id ? (
                      <Link to="/invoices" className="inline-block"><StatusBadge status="invoiced" /></Link>
                    ) : (
                      <StatusBadge status={w.payment_status} />
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {w.payment_status === "unpaid" && (
                      <button onClick={() => handleMarkPaid(w.id)} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium flex items-center gap-1" data-testid={`mark-paid-${w.id}`}>
                        <CheckCircle className="w-3.5 h-3.5" />Paid
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

function MetricCard({ label, value, accent = "slate" }) {
  const bar = { rose: "bg-rose-400", emerald: "bg-emerald-400", violet: "bg-violet-400", slate: "bg-slate-200" }[accent] || "bg-slate-200";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${bar}`} />
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">{label}</p>
      <p className="text-2xl font-bold text-slate-900 tabular-nums leading-none">{value}</p>
    </div>
  );
}

export default Financials;
