import { useState, useMemo, useCallback } from "react";
import { toast } from "sonner";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { CheckCircle, FileText, HardHat, Building2 } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { DataTable } from "@/components/DataTable";
import { StatCard } from "@/components/StatCard";
import { CreateInvoiceModal } from "../components/CreateInvoiceModal";
import { useFinancialSummary } from "@/hooks/useFinancials";
import { useWithdrawals, useMarkPaid, useBulkMarkPaid } from "@/hooks/useWithdrawals";
import { valueFormatter } from "@/lib/chartConfig";
import { dateToISO, endOfDayISO } from "@/lib/utils";

const Financials = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "");
  const [entityFilter, setEntityFilter] = useState(searchParams.get("entity") || "");
  const [dateRange, setDateRange] = useState(() => ({
    from: searchParams.get("from") ? new Date(searchParams.get("from")) : null,
    to: searchParams.get("to") ? new Date(searchParams.get("to")) : null,
  }));
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [createInvoiceModalOpen, setCreateInvoiceModalOpen] = useState(false);

  const syncFiltersToURL = useCallback((updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [key, val] of Object.entries(updates)) {
        if (val) next.set(key, val);
        else next.delete(key);
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const params = useMemo(() => ({
    payment_status: statusFilter || undefined,
    billing_entity: entityFilter || undefined,
    start_date: dateToISO(dateRange.from),
    end_date: endOfDayISO(dateRange.to),
  }), [statusFilter, entityFilter, dateRange]);

  const { data: summary, isLoading: summaryLoading } = useFinancialSummary(params);
  const { data: withdrawals = [], isLoading: wdLoading } = useWithdrawals(params);
  const markPaid = useMarkPaid();
  const bulkMarkPaid = useBulkMarkPaid();

  const handleMarkPaid = async (id, e) => {
    e?.stopPropagation();
    try {
      await markPaid.mutateAsync({ id });
      toast.success("Marked as paid");
    } catch { toast.error("Failed to mark as paid"); }
  };

  const handleBulkMarkPaid = async () => {
    if (selectedIds.size === 0) return;
    try {
      await bulkMarkPaid.mutateAsync(Array.from(selectedIds));
      toast.success(`Marked ${selectedIds.size} as paid`);
      setSelectedIds(new Set());
    } catch { toast.error("Failed to mark as paid"); }
  };

  const selectAllUnpaid = () => {
    setSelectedIds(new Set(
      withdrawals.filter((w) => w.payment_status === "unpaid" && !w.invoice_id).map((w) => w.id)
    ));
  };

  const selectedUnpaidIds = useMemo(
    () => [...selectedIds].filter((id) => {
      const w = withdrawals.find((x) => x.id === id);
      return w?.payment_status === "unpaid" && !w?.invoice_id;
    }),
    [selectedIds, withdrawals]
  );

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

  const columns = useMemo(() => [
    {
      key: "created_at",
      label: "Date",
      render: (row) => <span className="font-mono text-xs text-slate-500">{new Date(row.created_at).toLocaleDateString()}</span>,
      exportValue: (row) => row.created_at,
    },
    {
      key: "contractor_name",
      label: "Contractor",
      render: (row) => (
        <div className="flex items-center gap-2">
          <HardHat className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <div>
            <p className="font-medium text-slate-800">{row.contractor_name}</p>
            <p className="text-[10px] text-slate-400">{row.contractor_company}</p>
          </div>
        </div>
      ),
      exportValue: (row) => `${row.contractor_name} (${row.contractor_company || ""})`,
    },
    {
      key: "job_id",
      label: "Job",
      render: (row) => <span className="font-mono text-xs">{row.job_id}</span>,
    },
    {
      key: "total",
      label: "Total",
      align: "right",
      render: (row) => <span className="font-semibold tabular-nums">${(row.total || 0).toFixed(2)}</span>,
      exportValue: (row) => (row.total || 0).toFixed(2),
    },
    {
      key: "cost_total",
      label: "Cost",
      align: "right",
      render: (row) => <span className="text-slate-500 tabular-nums">${(row.cost_total || 0).toFixed(2)}</span>,
      exportValue: (row) => (row.cost_total || 0).toFixed(2),
    },
    {
      key: "_margin",
      label: "Margin",
      align: "right",
      sortable: false,
      searchable: false,
      render: (row) => <span className="text-emerald-600 tabular-nums">${((row.total || 0) - (row.cost_total || 0)).toFixed(2)}</span>,
      exportValue: (row) => ((row.total || 0) - (row.cost_total || 0)).toFixed(2),
    },
    {
      key: "payment_status",
      label: "Status",
      render: (row) =>
        row.payment_status === "invoiced" && row.invoice_id ? (
          <Link to="/invoices" className="inline-block" onClick={(e) => e.stopPropagation()}>
            <StatusBadge status="invoiced" />
          </Link>
        ) : (
          <StatusBadge status={row.payment_status} />
        ),
      exportValue: (row) => row.payment_status,
    },
  ], []);

  if (summaryLoading && wdLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="financials-page">
      <div className="flex flex-col gap-4 mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Financials</h1>
            <p className="text-slate-500 mt-1 text-sm">Payments, invoicing, and exports</p>
          </div>
          <div className="flex gap-2">
            <Link to="/invoices"><Button variant="outline" size="sm" className="gap-2"><FileText className="w-4 h-4" />Invoices</Button></Link>
          </div>
        </div>
        <DateRangeFilter value={dateRange} onChange={(r) => {
          setDateRange(r);
          syncFiltersToURL({ from: r.from?.toISOString()?.slice(0, 10), to: r.to?.toISOString()?.slice(0, 10) });
        }} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6" data-testid="summary-cards">
        <StatCard label="Unpaid" value={valueFormatter(summary?.total_unpaid || 0)} accent="rose" />
        <StatCard label="Paid" value={valueFormatter(summary?.total_paid || 0)} accent="emerald" />
        <StatCard label="Total Revenue" value={valueFormatter(summary?.total_revenue || 0)} />
        <StatCard label="Gross Margin" value={valueFormatter(summary?.gross_margin || 0)} accent="violet" />
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
          <Select value={statusFilter || "all"} onValueChange={(v) => { const val = v === "all" ? "" : v; setStatusFilter(val); syncFiltersToURL({ status: val }); }}>
            <SelectTrigger className="w-[140px] h-9"><SelectValue placeholder="All Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="unpaid">Unpaid</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
              <SelectItem value="invoiced">Invoiced</SelectItem>
            </SelectContent>
          </Select>
          <Select value={entityFilter || "all"} onValueChange={(v) => { const val = v === "all" ? "" : v; setEntityFilter(val); syncFiltersToURL({ entity: val }); }}>
            <SelectTrigger className="w-[160px] h-9"><SelectValue placeholder="All Entities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              {billingEntities.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          {(statusFilter || entityFilter) && (
            <button onClick={() => { setStatusFilter(""); setEntityFilter(""); syncFiltersToURL({ status: "", entity: "" }); }} className="text-xs text-slate-400 hover:text-slate-600">Clear</button>
          )}
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-orange-700">{selectedIds.size} selected</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>Clear</Button>
            {selectedUnpaidIds.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setCreateInvoiceModalOpen(true)} className="gap-1"><FileText className="w-3.5 h-3.5" />Invoice ({selectedUnpaidIds.length})</Button>
            )}
            <Button size="sm" onClick={handleBulkMarkPaid} data-testid="bulk-mark-paid-btn" className="gap-1"><CheckCircle className="w-3.5 h-3.5" />Mark Paid</Button>
          </div>
        </div>
      )}

      <CreateInvoiceModal open={createInvoiceModalOpen} onOpenChange={setCreateInvoiceModalOpen} onCreated={() => { setSelectedIds(new Set()); }} preselectedIds={selectedUnpaidIds} />

      <DataTable
        data={withdrawals}
        columns={columns}
        title="Transactions"
        emptyMessage="No transactions found"
        searchable
        exportable
        exportFilename={`financials-${format(new Date(), "yyyyMMdd")}.csv`}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        isSelectable={(row) => !row.invoice_id}
        headerActions={
          <button onClick={selectAllUnpaid} className="text-xs text-orange-500 hover:text-orange-600 font-medium">Select All Unpaid</button>
        }
        rowActions={(w) =>
          w.payment_status === "unpaid" ? (
            <button onClick={(e) => handleMarkPaid(w.id, e)} className="text-xs text-emerald-600 hover:text-emerald-700 font-medium flex items-center gap-1" data-testid={`mark-paid-${w.id}`}>
              <CheckCircle className="w-3.5 h-3.5" />Paid
            </button>
          ) : null
        }
      />
    </div>
  );
};

export default Financials;
