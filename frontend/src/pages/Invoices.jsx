import { useState, useMemo } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { FileText, Plus, Send, ArrowRight, CheckSquare, Square } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { CreateInvoiceModal } from "../components/CreateInvoiceModal";
import { InvoiceDetailModal } from "../components/InvoiceDetailModal";
import { useInvoices, useSyncXero, useBulkSyncXero } from "@/hooks/useInvoices";

const Invoices = () => {
  const [statusFilter, setStatusFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [detailInvoiceId, setDetailInvoiceId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const params = useMemo(() => ({
    status: statusFilter || undefined,
    billing_entity: entityFilter || undefined,
  }), [statusFilter, entityFilter]);

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

  const toggleSelect = (id, e) => {
    e?.stopPropagation();
    setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };

  const toggleSelectAll = () => setSelectedIds(selectedIds.size >= invoices.length ? new Set() : new Set(invoices.map((i) => i.id)));

  const statusSummary = useMemo(() => {
    const groups = { draft: [], sent: [], paid: [] };
    invoices.forEach((i) => groups[i.status]?.push(i));
    return Object.entries(groups).filter(([, arr]) => arr.length > 0).map(([status, arr]) => ({
      status, count: arr.length, total: arr.reduce((s, i) => s + (i.total ?? 0), 0),
    }));
  }, [invoices]);

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="invoices-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Invoices</h1>
          <Link to="/financials" className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 mt-1 transition-colors">Financials <ArrowRight className="w-3 h-3" /></Link>
        </div>
        <Button onClick={() => setCreateModalOpen(true)} size="sm" className="gap-2" data-testid="create-invoice-btn"><Plus className="w-4 h-4" />Create Invoice</Button>
      </div>

      {statusSummary.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-6">
          {statusSummary.map(({ status, count, total }) => {
            const cls = { draft: "bg-slate-50 border-slate-200 text-slate-700", sent: "bg-blue-50 border-blue-200 text-blue-700", paid: "bg-emerald-50 border-emerald-200 text-emerald-700" }[status];
            return <div key={status} className={`px-3 py-1.5 rounded-lg border text-xs ${cls}`}><span className="font-semibold">{count} {status}</span><span className="opacity-60 ml-1">· ${total.toFixed(2)}</span></div>;
          })}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Filter</span>
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[130px] h-9"><SelectValue placeholder="All Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
            </SelectContent>
          </Select>
          <Select value={entityFilter || "all"} onValueChange={(v) => setEntityFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[160px] h-9"><SelectValue placeholder="All Entities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              {billingEntities.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          {(statusFilter || entityFilter) && <button onClick={() => { setStatusFilter(""); setEntityFilter(""); }} className="text-xs text-slate-400 hover:text-slate-600">Clear</button>}
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

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-100">
              <th className="w-10 px-3 py-2.5"><button type="button" onClick={toggleSelectAll} className="text-slate-400 hover:text-slate-600">{selectedIds.size >= invoices.length && invoices.length > 0 ? <CheckSquare className="w-4 h-4 text-blue-600" /> : <Square className="w-4 h-4" />}</button></th>
              <th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Invoice #</th>
              <th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Entity</th>
              <th className="text-right text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Total</th>
              <th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Status</th>
              <th className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Date</th>
              <th className="text-right text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 px-3 py-2.5">Wds</th>
              <th className="w-[140px] px-3 py-2.5" />
            </tr></thead>
            <tbody className="divide-y divide-slate-50">
              {invoices.length === 0 ? (
                <tr><td colSpan="8" className="text-center py-12 text-slate-400 text-sm">No invoices yet</td></tr>
              ) : invoices.map((inv) => (
                <tr key={inv.id} className={`cursor-pointer hover:bg-slate-50/60 transition-colors ${selectedIds.has(inv.id) ? "bg-blue-50/40" : ""}`} onClick={() => setDetailInvoiceId(inv.id)}>
                  <td className="px-3 py-2.5" onClick={(e) => toggleSelect(inv.id, e)}>{selectedIds.has(inv.id) ? <CheckSquare className="w-4 h-4 text-blue-600" /> : <Square className="w-4 h-4 text-slate-300" />}</td>
                  <td className="px-3 py-2.5 font-mono text-xs font-medium">{inv.invoice_number}</td>
                  <td className="px-3 py-2.5 text-slate-600">{inv.billing_entity || "—"}</td>
                  <td className="px-3 py-2.5 text-right font-semibold tabular-nums">${(inv.total ?? 0).toFixed(2)}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={inv.status} /></td>
                  <td className="px-3 py-2.5 font-mono text-xs text-slate-500">{inv.created_at ? format(new Date(inv.created_at), "MMM d, yyyy") : "—"}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-slate-500">{inv.withdrawal_count ?? 0}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={(e) => { e.stopPropagation(); setDetailInvoiceId(inv.id); }} className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"><FileText className="w-3.5 h-3.5" />View</button>
                      <button onClick={(e) => handleSendToXero(inv.id, e)} disabled={syncXero.isPending} className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1 ml-2"><Send className="w-3.5 h-3.5" />Xero</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <CreateInvoiceModal open={createModalOpen} onOpenChange={setCreateModalOpen} onCreated={(inv) => setDetailInvoiceId(inv?.id)} />
      <InvoiceDetailModal invoiceId={detailInvoiceId} open={!!detailInvoiceId} onOpenChange={(open) => !open && setDetailInvoiceId(null)} onSaved={() => {}} onDeleted={() => setDetailInvoiceId(null)} />
    </div>
  );
};

export default Invoices;
