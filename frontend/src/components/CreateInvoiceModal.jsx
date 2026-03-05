import { useState, useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { toast } from "sonner";
import { useWithdrawals } from "@/hooks/useWithdrawals";
import { useCreateInvoice } from "@/hooks/useInvoices";

export function CreateInvoiceModal({ open, onOpenChange, onCreated, preselectedIds = [] }) {
  const [entityFilter, setEntityFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set(preselectedIds));

  const { data: withdrawals = [], isLoading } = useWithdrawals(
    open ? { payment_status: "unpaid" } : null
  );
  const createInvoice = useCreateInvoice();

  useEffect(() => {
    if (open) setSelectedIds(new Set(preselectedIds));
  }, [open, preselectedIds]);

  const { entities, filtered } = useMemo(() => {
    const byEntity = {};
    withdrawals.forEach((w) => {
      const be = w.billing_entity || "(No entity)";
      (byEntity[be] ||= []).push(w);
    });
    return {
      entities: Object.keys(byEntity).sort(),
      filtered: entityFilter ? (byEntity[entityFilter] || []) : withdrawals,
    };
  }, [withdrawals, entityFilter]);

  const eligible = filtered.filter((w) => !w.invoice_id);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleCreate = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      const inv = await createInvoice.mutateAsync({ withdrawal_ids: ids });
      toast.success("Invoice created");
      onCreated?.(inv);
      onOpenChange(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create invoice");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl rounded-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Create Invoice</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-600">
          Select uninvoiced withdrawals. All must share the same billing entity.
        </p>

        <div className="flex items-center gap-3">
          <label className="text-sm font-medium">Billing Entity</label>
          <Select value={entityFilter || "all"} onValueChange={(v) => setEntityFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[200px]"><SelectValue placeholder="All entities" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All entities</SelectItem>
              {entities.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => setSelectedIds((prev) => new Set([...prev, ...eligible.map((w) => w.id)]))}>
            Select all in list
          </Button>
        </div>

        <div className="flex-1 overflow-auto border border-slate-200 rounded-lg min-h-[200px]">
          {isLoading ? (
            <div className="p-6 text-center text-slate-500">Loading…</div>
          ) : eligible.length === 0 ? (
            <div className="p-6 text-center text-slate-500">
              No uninvoiced withdrawals{entityFilter ? ` for ${entityFilter}` : ""}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="w-10 px-3 py-2"></th>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-left">Job ID</th>
                  <th className="px-3 py-2 text-left">Entity</th>
                  <th className="px-3 py-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {eligible.map((w) => (
                  <tr key={w.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={selectedIds.has(w.id)} onChange={() => toggleSelect(w.id)} className="w-4 h-4 rounded border-slate-300" />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{new Date(w.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-2 font-mono">{w.job_id}</td>
                    <td className="px-3 py-2">{w.billing_entity || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">${w.total?.toFixed(2) || "0.00"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex justify-between items-center pt-4 border-t">
          <span className="text-sm text-slate-600">{selectedIds.size} withdrawal(s) selected</span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={selectedIds.size === 0 || createInvoice.isPending}>
              {createInvoice.isPending ? "Creating…" : "Create Invoice"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
