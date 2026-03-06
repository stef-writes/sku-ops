import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { FileText, HardHat } from "lucide-react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { StatCard } from "@/components/StatCard";
import { StatusBadge } from "@/components/StatusBadge";
import { DataTable } from "@/components/DataTable";
import { ViewToolbar } from "@/components/ViewToolbar";
import { CreateInvoiceModal } from "@/components/CreateInvoiceModal";
import { WithdrawalDetailPanel } from "@/components/WithdrawalDetailPanel";
import { InvoiceDetailModal } from "@/components/InvoiceDetailModal";
import { JobDetailPanel } from "@/components/JobDetailPanel";
import { useWithdrawals } from "@/hooks/useWithdrawals";
import { useViewController } from "@/hooks/useViewController";

const buildColumns = (onViewJob) => [
  {
    key: "created_at",
    label: "Date",
    type: "date",
    render: (row) => (
      <span className="font-mono text-xs text-muted-foreground">
        {new Date(row.created_at).toLocaleDateString()}
      </span>
    ),
    exportValue: (row) => row.created_at,
  },
  {
    key: "contractor_name",
    label: "Contractor",
    type: "text",
    render: (row) => (
      <div className="flex items-center gap-2">
        <HardHat className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <div>
          <p className="font-medium text-foreground">{row.contractor_name}</p>
          <p className="text-[10px] text-muted-foreground">{row.contractor_company}</p>
        </div>
      </div>
    ),
    exportValue: (row) => `${row.contractor_name} (${row.contractor_company || ""})`,
  },
  {
    key: "job_id",
    label: "Job",
    type: "text",
    render: (row) =>
      row.job_id ? (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onViewJob(row.job_id); }}
          className="font-mono text-xs text-info hover:text-info hover:underline"
        >
          {row.job_id}
        </button>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      ),
  },
  { key: "billing_entity", label: "Entity", type: "enum" },
  {
    key: "total",
    label: "Total",
    type: "number",
    align: "right",
    render: (row) => <span className="font-semibold tabular-nums">${(row.total || 0).toFixed(2)}</span>,
    exportValue: (row) => (row.total || 0).toFixed(2),
  },
  {
    key: "cost_total",
    label: "Cost",
    type: "number",
    align: "right",
    render: (row) => <span className="text-muted-foreground tabular-nums">${(row.cost_total || 0).toFixed(2)}</span>,
    exportValue: (row) => (row.cost_total || 0).toFixed(2),
  },
  {
    key: "_margin",
    label: "Margin",
    type: "number",
    sortable: false,
    filterable: false,
    searchable: false,
    render: (row) => <span className="text-success tabular-nums">${((row.total || 0) - (row.cost_total || 0)).toFixed(2)}</span>,
    exportValue: (row) => ((row.total || 0) - (row.cost_total || 0)).toFixed(2),
  },
  {
    key: "_invoice_status",
    label: "Status",
    type: "enum",
    sortable: false,
    filterable: false,
    render: (row) =>
      row.invoice_id ? (
        <Link to="/invoices" className="inline-block" onClick={(e) => e.stopPropagation()}>
          <StatusBadge status="invoiced" />
        </Link>
      ) : (
        <StatusBadge status="uninvoiced" />
      ),
    exportValue: (row) => (row.invoice_id ? "invoiced" : "uninvoiced"),
  },
];

export function TransactionsTable({ dateParams }) {
  const { data: withdrawals = [] } = useWithdrawals(dateParams);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [createInvoiceModalOpen, setCreateInvoiceModalOpen] = useState(false);
  const [detailWithdrawalId, setDetailWithdrawalId] = useState(null);
  const [detailInvoiceId, setDetailInvoiceId] = useState(null);
  const [detailJobId, setDetailJobId] = useState(null);

  const columns = useMemo(() => buildColumns(setDetailJobId), []);
  const view = useViewController({ columns });
  const processed = view.apply(withdrawals);

  const selectAllUninvoiced = () => {
    setSelectedIds(new Set(withdrawals.filter((w) => !w.invoice_id).map((w) => w.id)));
  };

  const selectedUninvoicedIds = useMemo(
    () => [...selectedIds].filter((id) => {
      const w = withdrawals.find((x) => x.id === id);
      return w && !w.invoice_id;
    }),
    [selectedIds, withdrawals],
  );

  const invoiceTotals = useMemo(() => {
    const uninvoiced = withdrawals.filter((w) => !w.invoice_id);
    const invoiced = withdrawals.filter((w) => !!w.invoice_id);
    return {
      uninvoicedTotal: uninvoiced.reduce((s, w) => s + (w.total || 0), 0),
      invoicedTotal: invoiced.reduce((s, w) => s + (w.total || 0), 0),
    };
  }, [withdrawals]);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <StatCard label="Uninvoiced" value={valueFormatter(invoiceTotals.uninvoicedTotal)} accent="amber" />
        <StatCard label="Invoiced" value={valueFormatter(invoiceTotals.invoicedTotal)} accent="blue" />
      </div>

      <ViewToolbar
        controller={view}
        columns={columns}
        data={withdrawals}
        resultCount={processed.length}
        className="mb-3"
        actions={
          <button onClick={selectAllUninvoiced} className="text-xs text-accent hover:text-accent font-medium">
            Select All Uninvoiced
          </button>
        }
      />

      {selectedIds.size > 0 && (
        <div className="bg-warning/10 border border-warning/30 rounded-xl p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-accent">{selectedIds.size} selected</span>
          <div className="flex gap-2">
            <button onClick={() => setSelectedIds(new Set())} className="text-xs text-muted-foreground hover:text-foreground px-2 py-1">Clear</button>
            {selectedUninvoicedIds.length > 0 && (
              <button
                onClick={() => setCreateInvoiceModalOpen(true)}
                className="inline-flex items-center gap-1 text-xs font-medium text-accent bg-card border border-warning/30 rounded-lg px-3 py-1.5 hover:bg-warning/10"
              >
                <FileText className="w-3.5 h-3.5" />
                Create Invoice ({selectedUninvoicedIds.length})
              </button>
            )}
          </div>
        </div>
      )}

      <DataTable
        data={processed}
        columns={view.visibleColumns}
        title="Transactions"
        emptyMessage="No transactions found"
        exportable
        exportFilename={`transactions-${format(new Date(), "yyyyMMdd")}.csv`}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        isSelectable={(row) => !row.invoice_id}
        onRowClick={(row) => setDetailWithdrawalId(row.id)}
        disableSort
      />

      <CreateInvoiceModal
        open={createInvoiceModalOpen}
        onOpenChange={setCreateInvoiceModalOpen}
        onCreated={() => setSelectedIds(new Set())}
        preselectedIds={selectedUninvoicedIds}
      />

      <WithdrawalDetailPanel
        withdrawalId={detailWithdrawalId}
        open={!!detailWithdrawalId}
        onOpenChange={(open) => !open && setDetailWithdrawalId(null)}
        onViewInvoice={(invoiceId) => { setDetailWithdrawalId(null); setDetailInvoiceId(invoiceId); }}
        onViewJob={(jobId) => { setDetailWithdrawalId(null); setDetailJobId(jobId); }}
      />

      <InvoiceDetailModal
        invoiceId={detailInvoiceId}
        open={!!detailInvoiceId}
        onOpenChange={(open) => !open && setDetailInvoiceId(null)}
        onSaved={() => {}}
        onDeleted={() => setDetailInvoiceId(null)}
      />

      <JobDetailPanel
        jobId={detailJobId}
        open={!!detailJobId}
        onOpenChange={(open) => !open && setDetailJobId(null)}
      />
    </>
  );
}
