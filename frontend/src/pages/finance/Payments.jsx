import { useState, useMemo } from "react";
import { DollarSign, CreditCard } from "lucide-react";
import { format } from "date-fns";
import { PageHeader } from "@/components/PageHeader";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { DataTable } from "@/components/DataTable";
import { ViewToolbar } from "@/components/ViewToolbar";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { PaymentDetailPanel } from "./_PaymentDetailPanel";
import { usePayments } from "@/hooks/usePayments";
import { useViewController } from "@/hooks/useViewController";
import { PAYMENT_METHODS } from "@/lib/constants";
import { dateToISO, endOfDayISO } from "@/lib/utils";

const methodMap = Object.fromEntries(PAYMENT_METHODS.map((m) => [m.value, m.label]));

const COLUMNS = [
  {
    key: "payment_date",
    label: "Date",
    type: "date",
    render: (row) => (
      <span className="font-mono text-xs text-slate-500">
        {row.payment_date ? format(new Date(row.payment_date), "MMM d, yyyy") : "—"}
      </span>
    ),
  },
  {
    key: "amount",
    label: "Amount",
    type: "number",
    align: "right",
    render: (row) => (
      <span className="font-bold font-mono text-slate-900 tabular-nums">
        ${(row.amount ?? 0).toFixed(2)}
      </span>
    ),
  },
  {
    key: "method",
    label: "Method",
    type: "enum",
    filterValues: PAYMENT_METHODS.map((m) => m.value),
    render: (row) => (
      <div className="flex items-center gap-2">
        <CreditCard className="w-3.5 h-3.5 text-slate-400" />
        <span className="text-sm text-slate-700">{methodMap[row.method] || row.method}</span>
      </div>
    ),
  },
  {
    key: "reference",
    label: "Reference",
    type: "text",
    render: (row) => (
      <span className="font-mono text-xs text-slate-500">{row.reference || "—"}</span>
    ),
  },
  {
    key: "invoice_id",
    label: "Invoice",
    type: "text",
    render: (row) => (
      <span className="font-mono text-xs text-slate-500">
        {row.invoice_id ? row.invoice_id.slice(0, 8) + "…" : "—"}
      </span>
    ),
  },
];

const Payments = () => {
  const [detailPaymentId, setDetailPaymentId] = useState(null);
  const [dateRange, setDateRange] = useState({ from: null, to: null });

  const dateParams = useMemo(
    () => ({
      start_date: dateToISO(dateRange.from),
      end_date: endOfDayISO(dateRange.to),
    }),
    [dateRange]
  );

  const { data: payments = [], isLoading } = usePayments(dateParams);

  const totalAmount = useMemo(
    () => payments.reduce((s, p) => s + (p.amount || 0), 0),
    [payments]
  );

  const view = useViewController({ columns: COLUMNS });
  const processed = view.apply(payments);

  if (isLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="payments-page">
      <PageHeader
        title="Payments"
        subtitle={`${payments.length} payment${payments.length !== 1 ? "s" : ""} · $${totalAmount.toFixed(2)} total`}
      />

      <DateRangeFilter value={dateRange} onChange={setDateRange} className="mb-6" />

      <ViewToolbar
        controller={view}
        columns={COLUMNS}
        data={payments}
        resultCount={processed.length}
        className="mb-3"
      />

      <DataTable
        data={processed}
        columns={view.visibleColumns}
        title="Payments"
        emptyMessage="No payments recorded"
        emptyIcon={DollarSign}
        onRowClick={(row) => setDetailPaymentId(row.id)}
        disableSort
      />

      <PaymentDetailPanel
        paymentId={detailPaymentId}
        open={!!detailPaymentId}
        onOpenChange={(open) => !open && setDetailPaymentId(null)}
      />

    </div>
  );
};

export default Payments;
