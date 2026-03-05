import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { FileText, Trash2, Plus, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  useInvoice,
  useUpdateInvoice,
  useDeleteInvoice,
  useSyncXero,
} from "@/hooks/useInvoices";

const PAYMENT_TERMS = [
  { value: "due_on_receipt", label: "Due on Receipt" },
  { value: "net_15", label: "Net 15" },
  { value: "net_30", label: "Net 30" },
  { value: "net_45", label: "Net 45" },
  { value: "net_60", label: "Net 60" },
  { value: "net_90", label: "Net 90" },
];

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "sent", label: "Sent" },
  { value: "paid", label: "Paid" },
];

const INITIAL_FORM = {
  billing_entity: "", contact_name: "", contact_email: "", notes: "",
  tax_rate: 0, status: "draft", invoice_date: "", due_date: "",
  payment_terms: "net_30", billing_address: "", po_reference: "",
};

export function InvoiceDetailModal({ invoiceId, open, onOpenChange, onSaved, onDeleted }) {
  const { data: invoice, isLoading } = useInvoice(open ? invoiceId : null);
  const updateInvoice = useUpdateInvoice();
  const deleteInvoice = useDeleteInvoice();
  const syncXero = useSyncXero();

  const [form, setForm] = useState(INITIAL_FORM);
  const [lineItems, setLineItems] = useState([]);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  useEffect(() => {
    if (invoice) {
      setForm({
        billing_entity: invoice.billing_entity || "",
        contact_name: invoice.contact_name || "",
        contact_email: invoice.contact_email || "",
        notes: invoice.notes || "",
        tax_rate: invoice.tax_rate ?? 0,
        status: invoice.status || "draft",
        invoice_date: invoice.invoice_date ? invoice.invoice_date.slice(0, 10) : "",
        due_date: invoice.due_date ? invoice.due_date.slice(0, 10) : "",
        payment_terms: invoice.payment_terms || "net_30",
        billing_address: invoice.billing_address || "",
        po_reference: invoice.po_reference || "",
      });
      setLineItems(invoice.line_items || []);
    }
  }, [invoice]);

  const updateLineItem = (idx, field, value) => {
    setLineItems((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      if (field === "quantity" || field === "unit_price") {
        next[idx].amount = Math.round((parseFloat(next[idx].quantity) || 0) * (parseFloat(next[idx].unit_price) || 0) * 100) / 100;
      }
      return next;
    });
  };

  const subtotal = lineItems.reduce((sum, i) => sum + (i.amount ?? (i.quantity ?? 0) * (i.unit_price ?? 0)), 0);
  const taxAmount = Math.round(subtotal * (parseFloat(form.tax_rate) || 0) * 100) / 100;
  const total = Math.round((subtotal + taxAmount) * 100) / 100;
  const canEdit = invoice?.status === "draft" || invoice?.status === "approved";

  const handleSave = async () => {
    if (!form.billing_entity?.trim()) return toast.error("Billing entity is required");
    if (form.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.contact_email)) return toast.error("Invalid contact email");
    if (lineItems.length === 0) return toast.error("At least one line item is required");

    const items = lineItems.map((i) => ({
      id: i.id, description: i.description || "",
      quantity: parseFloat(i.quantity) || 0, unit_price: parseFloat(i.unit_price) || 0,
      amount: (parseFloat(i.quantity) || 0) * (parseFloat(i.unit_price) || 0),
      product_id: i.product_id,
    }));

    try {
      await updateInvoice.mutateAsync({
        id: invoiceId,
        data: {
          ...form,
          tax: taxAmount,
          tax_rate: parseFloat(form.tax_rate) || 0,
          invoice_date: form.invoice_date || undefined,
          due_date: form.due_date || undefined,
          payment_terms: form.payment_terms || undefined,
          billing_address: form.billing_address || undefined,
          po_reference: form.po_reference || undefined,
          line_items: items,
        },
      });
      toast.success("Invoice saved");
      onSaved?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save");
    }
  };

  const handleDelete = async () => {
    try {
      await deleteInvoice.mutateAsync(invoiceId);
      toast.success("Invoice deleted");
      onDeleted?.();
      onOpenChange(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to delete");
      throw err;
    }
  };

  const handleSyncXero = async () => {
    try {
      const res = await syncXero.mutateAsync(invoiceId);
      toast.info(res?.message || "Xero sync queued");
    } catch {
      toast.error("Failed");
    }
  };

  if (!invoice && !isLoading) return null;

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl rounded-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-slate-500" />
            <span>{invoice?.invoice_number || "Invoice"}</span>
            {invoice && <StatusBadge status={invoice.status} />}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8 text-center text-slate-500">Loading…</div>
        ) : (
          <div className="flex-1 overflow-auto space-y-6">
            <div>
              <Label className="text-xs uppercase text-slate-500">Invoice Details</Label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
                <div>
                  <label className="text-xs text-slate-500">Invoice Date</label>
                  <Input type="date" value={form.invoice_date} onChange={(e) => setForm((f) => ({ ...f, invoice_date: e.target.value }))} disabled={!canEdit} className="mt-0.5" />
                </div>
                <div>
                  <label className="text-xs text-slate-500">Due Date</label>
                  <Input type="date" value={form.due_date} onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} disabled={!canEdit} className="mt-0.5" />
                </div>
                <div>
                  <label className="text-xs text-slate-500">Payment Terms</label>
                  <Select value={form.payment_terms} onValueChange={(v) => setForm((f) => ({ ...f, payment_terms: v }))} disabled={!canEdit}>
                    <SelectTrigger className="mt-0.5"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_TERMS.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs text-slate-500">PO Reference</label>
                  <Input value={form.po_reference} onChange={(e) => setForm((f) => ({ ...f, po_reference: e.target.value }))} disabled={!canEdit} className="mt-0.5" placeholder="Contractor PO #" />
                </div>
              </div>
            </div>

            <div>
              <Label className="text-xs uppercase text-slate-500">Bill To</Label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                {[
                  { key: "billing_entity", label: "Billing Entity" },
                  { key: "contact_name", label: "Contact Name" },
                  { key: "contact_email", label: "Contact Email", type: "email" },
                  { key: "billing_address", label: "Billing Address", placeholder: "Street, City, State ZIP" },
                ].map((f) => (
                  <div key={f.key}>
                    <label className="text-xs text-slate-500">{f.label}</label>
                    <Input
                      type={f.type || "text"}
                      value={form[f.key]}
                      onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                      disabled={!canEdit}
                      className="mt-0.5"
                      placeholder={f.placeholder}
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <Label className="text-xs uppercase text-slate-500">Line Items</Label>
                {canEdit && (
                  <Button variant="ghost" size="sm" onClick={() => setLineItems([...lineItems, { id: crypto.randomUUID(), description: "", quantity: 1, unit_price: 0, amount: 0 }])}>
                    <Plus className="w-4 h-4 mr-1" /> Add row
                  </Button>
                )}
              </div>
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="px-3 py-2 text-left">Description</th>
                      <th className="px-3 py-2 text-right w-20">Qty</th>
                      <th className="px-3 py-2 text-right w-24">Unit $</th>
                      <th className="px-3 py-2 text-right w-24">Amount</th>
                      {canEdit && <th className="w-10"></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {lineItems.map((item, idx) => (
                      <tr key={item.id || idx} className="border-b border-slate-100">
                        <td className="px-3 py-2">
                          {canEdit ? <Input value={item.description || ""} onChange={(e) => updateLineItem(idx, "description", e.target.value)} className="h-8 text-sm" /> : (item.description || "—")}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {canEdit ? <Input type="number" min={0} step={0.01} value={item.quantity ?? ""} onChange={(e) => updateLineItem(idx, "quantity", e.target.value)} className="h-8 w-20 text-right" /> : item.quantity}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {canEdit ? <Input type="number" min={0} step={0.01} value={item.unit_price ?? ""} onChange={(e) => updateLineItem(idx, "unit_price", e.target.value)} className="h-8 w-24 text-right" /> : `$${(item.unit_price ?? 0).toFixed(2)}`}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">${(item.amount ?? (item.quantity ?? 0) * (item.unit_price ?? 0)).toFixed(2)}</td>
                        {canEdit && (
                          <td><Button variant="ghost" size="sm" className="text-red-600 h-8 w-8 p-0" onClick={() => setLineItems(lineItems.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4" /></Button></td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-end">
              <div className="w-72 space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Subtotal</span>
                  <span className="font-mono">${subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm items-center gap-2">
                  <span className="text-slate-500">Tax Rate</span>
                  {canEdit ? (
                    <div className="flex items-center gap-1">
                      <Input type="number" min={0} max={100} step={0.1} value={((parseFloat(form.tax_rate) || 0) * 100).toFixed(1)} onChange={(e) => { const rate = (parseFloat(e.target.value) || 0) / 100; setForm((f) => ({ ...f, tax_rate: rate })); }} className="w-20 h-8 text-right" />
                      <span className="text-xs text-slate-400">%</span>
                    </div>
                  ) : (
                    <span className="font-mono">{((parseFloat(form.tax_rate) || 0) * 100).toFixed(1)}%</span>
                  )}
                </div>
                <div className="flex justify-between text-sm items-center">
                  <span className="text-slate-500">Tax</span>
                  <span className="font-mono">${taxAmount.toFixed(2)}</span>
                </div>
                <div className="flex justify-between font-bold pt-2 border-t">
                  <span>Total</span>
                  <span className="font-mono">${total.toFixed(2)}</span>
                </div>
                {(invoice?.amount_credited ?? 0) > 0 && (
                  <>
                    <div className="flex justify-between text-sm text-green-600">
                      <span>Credits Applied</span>
                      <span className="font-mono">-${(invoice.amount_credited ?? 0).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between font-bold">
                      <span>Balance Due</span>
                      <span className="font-mono">${(total - (invoice.amount_credited ?? 0)).toFixed(2)}</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div>
              <Label className="text-xs uppercase text-slate-500">Notes</Label>
              {canEdit ? (
                <Textarea value={form.notes || ""} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} className="mt-1 min-h-[60px]" placeholder="Optional notes" />
              ) : (
                <p className="mt-1 text-sm text-slate-600">{invoice?.notes || "—"}</p>
              )}
            </div>

            {invoice?.withdrawal_ids?.length > 0 && (
              <div>
                <Label className="text-xs uppercase text-slate-500">Linked Withdrawals</Label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {invoice.withdrawal_ids.map((wid) => (
                    <Link key={wid} to="/financials" className="px-2 py-1 bg-slate-100 rounded font-mono text-xs hover:bg-slate-200 hover:underline" title={wid}>
                      {wid.slice(0, 8)}…
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {canEdit && (
              <div>
                <Label className="text-xs uppercase text-slate-500">Status</Label>
                <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
                  <SelectTrigger className="mt-1 w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between pt-4 border-t">
          <div>
            {canEdit && (
              <Button variant="outline" className="text-red-600 hover:text-red-700 hover:bg-red-50" onClick={() => setDeleteConfirmOpen(true)}>
                <Trash2 className="w-4 h-4 mr-2" /> Delete
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleSyncXero} disabled={syncXero.isPending}>
              <ExternalLink className="w-4 h-4 mr-2" /> Send to Xero
            </Button>
            {canEdit && (
              <Button onClick={handleSave} disabled={updateInvoice.isPending}>
                {updateInvoice.isPending ? "Saving…" : "Save"}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      open={deleteConfirmOpen}
      onOpenChange={setDeleteConfirmOpen}
      title="Delete draft invoice"
      description="Delete this draft invoice? Withdrawals will be unlinked."
      confirmLabel="Delete"
      cancelLabel="Cancel"
      onConfirm={handleDelete}
      variant="danger"
    />
    </>
  );
}
