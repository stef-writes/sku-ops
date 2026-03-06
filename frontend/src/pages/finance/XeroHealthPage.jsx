import { toast } from "sonner";
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useXeroHealth, useTriggerXeroSync } from "@/hooks/useXeroHealth";
import { getErrorMessage } from "@/lib/api-client";

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

function formatMoney(val) {
  if (val == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
}

function SectionHeader({ icon: Icon, label, count, variant = "neutral" }) {
  const colors = {
    neutral: "text-muted-foreground",
    warn: "text-accent",
    danger: "text-destructive",
    ok: "text-success",
  };
  return (
    <div className="flex items-center gap-2 mb-2">
      <Icon className={`w-4 h-4 ${colors[variant]}`} />
      <h2 className="font-semibold text-foreground text-sm">{label}</h2>
      <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${
        count === 0 ? "bg-muted text-muted-foreground" : "bg-warning/15 text-accent"
      }`}>
        {count}
      </span>
    </div>
  );
}

function EmptyRow() {
  return (
    <tr>
      <td colSpan={99} className="px-4 py-3 text-xs text-muted-foreground italic">
        None — all clear
      </td>
    </tr>
  );
}

function DocTable({ rows, columns }) {
  return (
    <div className="rounded-lg border border-border overflow-hidden mb-6">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted border-b border-border">
            {columns.map((col) => (
              <th key={col.key} className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {rows.length === 0 ? (
            <EmptyRow />
          ) : (
            rows.map((row, i) => (
              <tr key={row.id ?? i} className="hover:bg-muted/60 transition-colors">
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-2.5 text-foreground">
                    {col.render ? col.render(row) : row[col.key] ?? "—"}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

const INVOICE_COLS = [
  { key: "invoice_number", label: "Invoice #" },
  { key: "billing_entity", label: "Billed to" },
  { key: "total", label: "Total", render: (r) => formatMoney(r.total) },
  { key: "status", label: "Status", render: (r) => <span className="capitalize">{r.status}</span> },
  { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
];

const CN_COLS = [
  { key: "credit_note_number", label: "Credit Note #" },
  { key: "billing_entity", label: "Billed to" },
  { key: "total", label: "Total", render: (r) => formatMoney(r.total) },
  { key: "status", label: "Status", render: (r) => <span className="capitalize">{r.status}</span> },
  { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
];

const PO_COLS = [
  { key: "vendor_name", label: "Vendor" },
  { key: "total", label: "Total", render: (r) => formatMoney(r.total) },
  { key: "document_date", label: "Doc Date", render: (r) => formatDate(r.document_date) },
  { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
];

const MISMATCH_INVOICE_COLS = [
  { key: "invoice_number", label: "Invoice #" },
  { key: "billing_entity", label: "Billed to" },
  { key: "total", label: "Local Total", render: (r) => formatMoney(r.total) },
  { key: "xero_invoice_id", label: "Xero ID", render: (r) => <span className="font-mono text-xs text-muted-foreground">{r.xero_invoice_id}</span> },
  { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
];

export default function XeroHealthPage() {
  const { data, isLoading, error } = useXeroHealth();
  const syncMutation = useTriggerXeroSync();

  const handleSync = () => {
    syncMutation.mutate(undefined, {
      onSuccess: (res) => {
        if (res.success) {
          const s = res.summary;
          toast.success(
            `Sync complete — ${s.invoices_synced} invoices, ${s.credit_notes_synced} credits, ${s.po_bills_synced} bills synced`
          );
        } else {
          toast.error(res.error || "Sync failed");
        }
      },
      onError: (err) => toast.error(getErrorMessage(err)),
    });
  };

  if (isLoading) {
    return (
      <div className="flex-1 p-6 flex items-center justify-center text-muted-foreground text-sm">
        Loading sync health…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 p-6 flex items-center justify-center text-destructive text-sm">
        Failed to load sync health
      </div>
    );
  }

  const totals = data?.totals ?? {};
  const allClear = totals.unsynced === 0 && totals.mismatch === 0 && totals.failed === 0;

  return (
    <div className="flex-1 p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Xero Sync Health</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Unsynced documents, reconciliation mismatches, and failed syncs.
          </p>
        </div>
        <Button
          onClick={handleSync}
          disabled={syncMutation.isPending}
          className="gap-2"
          variant="outline"
        >
          <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
          {syncMutation.isPending ? "Syncing…" : "Run Sync Now"}
        </Button>
      </div>

      {allClear && (
        <div className="flex items-center gap-2 text-success bg-success/10 border border-success/30 rounded-lg px-4 py-3 text-sm font-medium">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          All documents are synced and reconciled — no exceptions.
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Unsynced", value: totals.unsynced, color: totals.unsynced > 0 ? "text-accent" : "text-muted-foreground" },
          { label: "Mismatches", value: totals.mismatch, color: totals.mismatch > 0 ? "text-destructive" : "text-muted-foreground" },
          { label: "Failed", value: totals.failed, color: totals.failed > 0 ? "text-destructive" : "text-muted-foreground" },
        ].map((stat) => (
          <div key={stat.label} className="bg-card border border-border rounded-lg p-4">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{stat.label}</p>
            <p className={`text-3xl font-bold mt-1 ${stat.color}`}>{stat.value ?? 0}</p>
          </div>
        ))}
      </div>

      <section>
        <SectionHeader icon={FileText} label="Unsynced Invoices" count={data?.unsynced_invoices?.length ?? 0} variant="warn" />
        <DocTable rows={data?.unsynced_invoices ?? []} columns={INVOICE_COLS} />
      </section>

      <section>
        <SectionHeader icon={FileText} label="Unsynced Credit Notes" count={data?.unsynced_credits?.length ?? 0} variant="warn" />
        <DocTable rows={data?.unsynced_credits ?? []} columns={CN_COLS} />
      </section>

      <section>
        <SectionHeader icon={FileText} label="Unsynced Vendor Bills (POs)" count={data?.unsynced_po_bills?.length ?? 0} variant="warn" />
        <DocTable rows={data?.unsynced_po_bills ?? []} columns={PO_COLS} />
      </section>

      <section>
        <SectionHeader icon={AlertTriangle} label="Invoice Mismatches" count={data?.mismatch_invoices?.length ?? 0} variant="danger" />
        <DocTable rows={data?.mismatch_invoices ?? []} columns={MISMATCH_INVOICE_COLS} />
      </section>

      <section>
        <SectionHeader icon={AlertTriangle} label="Credit Note Mismatches" count={data?.mismatch_credits?.length ?? 0} variant="danger" />
        <DocTable rows={data?.mismatch_credits ?? []} columns={CN_COLS} />
      </section>

      <section>
        <SectionHeader icon={XCircle} label="Failed Invoices" count={data?.failed_invoices?.length ?? 0} variant="danger" />
        <DocTable rows={data?.failed_invoices ?? []} columns={INVOICE_COLS} />
      </section>

      <section>
        <SectionHeader icon={XCircle} label="Failed Credit Notes" count={data?.failed_credits?.length ?? 0} variant="danger" />
        <DocTable rows={data?.failed_credits ?? []} columns={CN_COLS} />
      </section>

      <section>
        <SectionHeader icon={XCircle} label="Failed Vendor Bills" count={data?.failed_po_bills?.length ?? 0} variant="danger" />
        <DocTable rows={data?.failed_po_bills ?? []} columns={PO_COLS} />
      </section>
    </div>
  );
}
