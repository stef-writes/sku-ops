import { useState, useMemo, useCallback } from "react";
import { toast } from "sonner";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { FileText, Plus, Send, ArrowRight } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { DataTable } from "@/components/DataTable";
import { CreateInvoiceModal } from "../components/CreateInvoiceModal";
import { InvoiceDetailModal } from "../components/InvoiceDetailModal";
import { useInvoices, useSyncXero, useBulkSyncXero } from "@/hooks/useInvoices";
import { dateToISO, endOfDayISO } from "@/lib/utils";

const Invoices = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "");
  const [entityFilter, setEntityFilter] = useState(searchParams.get("entity") || "");
  const [dateRange, setDateRange] = useState(() => ({
    from: searchParams.get("from") ? new Date(searchParams.get("from")) : null,
    to: searchParams.get("to") ? new Date(searchParams.get("to")) : null,
  }));

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
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [detailInvoiceId, setDetailInvoiceId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const params = useMemo(() => ({
    status: statusFilter || undefined,
    billing_entity: entityFilter || undefined,
    start_date: dateToISO(dateRange.from),
    end_date: endOfDayISO(dateRange.to),
  }), [statusFilter, entityFilter, dateRange]);

  const { data: invoices = [], isLoading } = useInvoices(params);
  const syncXero = useSyncXero();
  const bulkSyncXero = useBulkSyncXero();

  const billingEntities = [...new Set(invoices.map((i) => i.billing_entity).filter(Boolean))].sort();

  const handleSendToXero = async (invoiceId, e) => {
    e?.stopPropagation();
    try {
      const res = await syncXero.mutateAsync(invoiceId);
      toast.info(res?.message || "Xero sync queued");
    } catch { toast.error("Failed to send to Xero"); }
  };

  const handleBulkSendToXero = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const res = await bulkSyncXero.mutateAsync(ids);
      toast.info(res?.message || `${res?.synced ?? 0} queued for Xero`);
      setSelectedIds(new Set());
    } catch { toast.error("Failed to bulk send to Xero"); }
  };

  const statusSummary = useMemo(() => {
    const groups = { draft: [], approved: [], sent: [], paid: [] };
    invoices.forEach((i) => groups[i.status]?.push(i));
    return Object.entries(groups).filter(([, arr]) => arr.length > 0).map(([status, arr]) => ({
      status, count: arr.length, total: arr.reduce((s, i) => s + (i.total ?? 0), 0),
    }));
  }, [invoices]);

  const columns = useMemo(() => [
    {
      key: "invoice_number",
      label: "Invoice #",
      render: (row) => <span className="font-mono text-xs font-medium">{row.invoice_number}</span>,
      exportValue: (row) => row.invoice_number,
    },
    {
      key: "billing_entity",
      label: "Entity",
      render: (row) => <span className="text-slate-600">{row.billing_entity || "—"}</span>,
    },
    {
      key: "total",
      label: "Total",
      align: "right",
      render: (row) => <span className="font-semibold tabular-nums">${(row.total ?? 0).toFixed(2)}</span>,
      exportValue: (row) => (row.total ?? 0).toFixed(2),
    },
    {
      key: "status",
      label: "Status",
      render: (row) => <StatusBadge status={row.status} />,
      exportValue: (row) => row.status,
    },
    {
      key: "invoice_date",
      label: "Date",
      render: (row) => {
        const d = row.invoice_date || row.created_at;
        return <span className="font-mono text-xs text-slate-500">{d ? format(new Date(d), "MMM d, yyyy") : "—"}</span>;
      },
      exportValue: (row) => row.invoice_date || row.created_at || "",
    },
    {
      key: "due_date",
      label: "Due",
      render: (row) => {
        if (!row.due_date) return "—";
        const overdue = row.status !== "paid" && new Date(row.due_date) < new Date();
        return (
          <span className={`font-mono text-xs ${overdue ? "text-red-600 font-semibold" : "text-slate-500"}`}>
            {format(new Date(row.due_date), "MMM d, yyyy")}
          </span>
        );
      },
      exportValue: (row) => row.due_date || "",
    },
    {
      key: "withdrawal_count",
      label: "Wds",
      align: "right",
      render: (row) => <span className="font-mono text-slate-500">{row.withdrawal_count ?? 0}</span>,
      sortable: true,
    },
  ], []);

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="invoices-page">
      <div className="flex flex-col gap-4 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Invoices</h1>
            <Link to="/financials" className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 mt-1 transition-colors">Financials <ArrowRight className="w-3 h-3" /></Link>
          </div>
          <Button onClick={() => setCreateModalOpen(true)} size="sm" className="gap-2" data-testid="create-invoice-btn"><Plus className="w-4 h-4" />Create Invoice</Button>
        </div>
        <DateRangeFilter value={dateRange} onChange={(r) => {
          setDateRange(r);
          syncFiltersToURL({ from: r.from?.toISOString()?.slice(0, 10), to: r.to?.toISOString()?.slice(0, 10) });
        }} />
      </div>

      {statusSummary.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-6">
          {statusSummary.map(({ status, count, total }) => {
            const cls = { draft: "bg-slate-50 border-slate-200 text-slate-700", approved: "bg-amber-50 border-amber-200 text-amber-700", sent: "bg-blue-50 border-blue-200 text-blue-700", paid: "bg-emerald-50 border-emerald-200 text-emerald-700" }[status];
            return <div key={status} className={`px-3 py-1.5 rounded-lg border text-xs ${cls}`}><span className="font-semibold">{count} {status}</span><span className="opacity-60 ml-1">· ${total.toFixed(2)}</span></div>;
          })}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Filter</span>
          <Select value={statusFilter || "all"} onValueChange={(v) => { const val = v === "all" ? "" : v; setStatusFilter(val); syncFiltersToURL({ status: val }); }}>
            <SelectTrigger className="w-[130px] h-9"><SelectValue placeholder="All Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
            </SelectContent>
          </Select>
          <Select value={entityFilter || "all"} onValueChange={(v) => { const val = v === "all" ? "" : v; setEntityFilter(val); syncFiltersToURL({ entity: val }); }}>
            <SelectTrigger className="w-[160px] h-9"><SelectValue placeholder="All Entities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              {billingEntities.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          {(statusFilter || entityFilter) && <button onClick={() => { setStatusFilter(""); setEntityFilter(""); syncFiltersToURL({ status: "", entity: "" }); }} className="text-xs text-slate-400 hover:text-slate-600">Clear dropdowns</button>}
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-slate-700">{selectedIds.size} selected</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>Clear</Button>
            <Button size="sm" onClick={handleBulkSendToXero} disabled={bulkSyncXero.isPending} className="bg-blue-600 hover:bg-blue-700 text-white gap-1"><Send className="w-3.5 h-3.5" />{bulkSyncXero.isPending ? "Sending…" : `Xero (${selectedIds.size})`}</Button>
          </div>
        </div>
      )}

      <DataTable
        data={invoices}
        columns={columns}
        title="Invoices"
        emptyMessage="No invoices yet"
        emptyIcon={FileText}
        searchable
        exportable
        exportFilename={`invoices-${format(new Date(), "yyyyMMdd")}.csv`}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        onRowClick={(row) => setDetailInvoiceId(row.id)}
        rowActions={(inv) => (
          <div className="flex items-center gap-1 justify-end">
            <button onClick={(e) => { e.stopPropagation(); setDetailInvoiceId(inv.id); }} className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"><FileText className="w-3.5 h-3.5" />View</button>
            <button onClick={(e) => handleSendToXero(inv.id, e)} disabled={syncXero.isPending} className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1 ml-2"><Send className="w-3.5 h-3.5" />Xero</button>
          </div>
        )}
      />

      <CreateInvoiceModal open={createModalOpen} onOpenChange={setCreateModalOpen} onCreated={(inv) => setDetailInvoiceId(inv?.id)} />
      <InvoiceDetailModal invoiceId={detailInvoiceId} open={!!detailInvoiceId} onOpenChange={(open) => !open && setDetailInvoiceId(null)} onSaved={() => {}} onDeleted={() => setDetailInvoiceId(null)} />
    </div>
  );
};

export default Invoices;
