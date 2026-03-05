import { useState, useMemo, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { FileText, HardHat, Building2, DollarSign as DollarSignIcon, Briefcase } from "lucide-react";
import { format } from "date-fns";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { DataTable } from "@/components/DataTable";
import { ViewToolbar } from "@/components/ViewToolbar";
import { StatCard } from "@/components/StatCard";
import { CreateInvoiceModal } from "../components/CreateInvoiceModal";
import { WithdrawalDetailPanel } from "@/components/WithdrawalDetailPanel";
import { InvoiceDetailModal } from "@/components/InvoiceDetailModal";
import { JobDetailPanel } from "@/components/JobDetailPanel";
import { useFinancialSummary } from "@/hooks/useFinancials";
import { useWithdrawals } from "@/hooks/useWithdrawals";
import { useViewController } from "@/hooks/useViewController";
import { valueFormatter } from "@/lib/chartConfig";
import { dateToISO, endOfDayISO } from "@/lib/utils";

const Financials = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [dateRange, setDateRange] = useState(() => ({
    from: searchParams.get("from") ? new Date(searchParams.get("from")) : null,
    to: searchParams.get("to") ? new Date(searchParams.get("to")) : null,
  }));
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [createInvoiceModalOpen, setCreateInvoiceModalOpen] = useState(false);
  const [detailWithdrawalId, setDetailWithdrawalId] = useState(null);
  const [detailInvoiceId, setDetailInvoiceId] = useState(null);
  const [detailJobId, setDetailJobId] = useState(null);

  const syncFiltersToURL = useCallback(
    (updates) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, val] of Object.entries(updates)) {
          if (val) next.set(key, val);
          else next.delete(key);
        }
        return next;
      }, { replace: true });
    },
    [setSearchParams]
  );

  const dateParams = useMemo(
    () => ({
      start_date: dateToISO(dateRange.from),
      end_date: endOfDayISO(dateRange.to),
    }),
    [dateRange]
  );

  const { data: summary, isLoading: summaryLoading } = useFinancialSummary(dateParams);
  const { data: withdrawals = [], isLoading: wdLoading } = useWithdrawals(dateParams);

  const selectAllUninvoiced = () => {
    setSelectedIds(
      new Set(
        withdrawals
          .filter((w) => !w.invoice_id)
          .map((w) => w.id)
      )
    );
  };

  const selectedUninvoicedIds = useMemo(
    () =>
      [...selectedIds].filter((id) => {
        const w = withdrawals.find((x) => x.id === id);
        return w && !w.invoice_id;
      }),
    [selectedIds, withdrawals]
  );

  const invoiceTotals = useMemo(() => {
    const uninvoiced = withdrawals.filter((w) => !w.invoice_id);
    const invoiced = withdrawals.filter((w) => !!w.invoice_id);
    return {
      uninvoicedTotal: uninvoiced.reduce((s, w) => s + (w.total || 0), 0),
      invoicedTotal: invoiced.reduce((s, w) => s + (w.total || 0), 0),
    };
  }, [withdrawals]);

  const columns = useMemo(
    () => [
      {
        key: "created_at",
        label: "Date",
        type: "date",
        render: (row) => (
          <span className="font-mono text-xs text-slate-500">
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
            <HardHat className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <div>
              <p className="font-medium text-slate-800">{row.contractor_name}</p>
              <p className="text-[10px] text-slate-400">{row.contractor_company}</p>
            </div>
          </div>
        ),
        exportValue: (row) =>
          `${row.contractor_name} (${row.contractor_company || ""})`,
      },
      {
        key: "job_id",
        label: "Job",
        type: "text",
        render: (row) => row.job_id ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setDetailJobId(row.job_id); }}
            className="font-mono text-xs text-blue-600 hover:text-blue-800 hover:underline"
          >
            {row.job_id}
          </button>
        ) : <span className="text-xs text-slate-400">—</span>,
      },
      {
        key: "billing_entity",
        label: "Entity",
        type: "enum",
      },
      {
        key: "total",
        label: "Total",
        type: "number",
        align: "right",
        render: (row) => (
          <span className="font-semibold tabular-nums">
            ${(row.total || 0).toFixed(2)}
          </span>
        ),
        exportValue: (row) => (row.total || 0).toFixed(2),
      },
      {
        key: "cost_total",
        label: "Cost",
        type: "number",
        align: "right",
        render: (row) => (
          <span className="text-slate-500 tabular-nums">
            ${(row.cost_total || 0).toFixed(2)}
          </span>
        ),
        exportValue: (row) => (row.cost_total || 0).toFixed(2),
      },
      {
        key: "_margin",
        label: "Margin",
        type: "number",
        sortable: false,
        filterable: false,
        searchable: false,
        render: (row) => (
          <span className="text-emerald-600 tabular-nums">
            ${((row.total || 0) - (row.cost_total || 0)).toFixed(2)}
          </span>
        ),
        exportValue: (row) =>
          ((row.total || 0) - (row.cost_total || 0)).toFixed(2),
      },
      {
        key: "_invoice_status",
        label: "Status",
        type: "enum",
        sortable: false,
        filterable: false,
        render: (row) =>
          row.invoice_id ? (
            <Link
              to="/invoices"
              className="inline-block"
              onClick={(e) => e.stopPropagation()}
            >
              <StatusBadge status="invoiced" />
            </Link>
          ) : (
            <StatusBadge status="uninvoiced" />
          ),
        exportValue: (row) => (row.invoice_id ? "invoiced" : "uninvoiced"),
      },
    ],
    []
  );

  const view = useViewController({ columns });
  const processedWithdrawals = view.apply(withdrawals);

  if (summaryLoading && wdLoading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="financials-page">
      <div className="flex flex-col gap-4 mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
              Financials
            </h1>
            <p className="text-slate-500 mt-1 text-sm">
              Invoicing, margins, and exports
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/invoices">
              <Button variant="outline" size="sm" className="gap-2">
                <FileText className="w-4 h-4" />
                Invoices
              </Button>
            </Link>
          </div>
        </div>
        <DateRangeFilter
          value={dateRange}
          onChange={(r) => {
            setDateRange(r);
            syncFiltersToURL({
              from: r.from?.toISOString()?.slice(0, 10),
              to: r.to?.toISOString()?.slice(0, 10),
            });
          }}
        />
      </div>

      <div
        className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6"
        data-testid="summary-cards"
      >
        <StatCard
          label="Uninvoiced"
          value={valueFormatter(invoiceTotals.uninvoicedTotal)}
          accent="amber"
        />
        <StatCard
          label="Invoiced"
          value={valueFormatter(invoiceTotals.invoicedTotal)}
          accent="blue"
        />
        <StatCard
          label="Total Revenue"
          value={valueFormatter(summary?.total_revenue || 0)}
        />
        <StatCard
          label="Gross Margin"
          value={valueFormatter(summary?.gross_margin || 0)}
          accent="violet"
        />
      </div>

      {summary?.by_contractor?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">
            Top Contractors by Spend
          </p>
          <div className="space-y-2">
            {[...summary.by_contractor]
              .sort((a, b) => (b.revenue ?? b.total ?? 0) - (a.revenue ?? a.total ?? 0))
              .slice(0, 8)
              .map((c, i) => {
                const amount = c.revenue ?? c.total ?? 0;
                const max = Math.max(...summary.by_contractor.map((x) => x.revenue ?? x.total ?? 0), 1);
                return (
                  <div key={c.contractor_id ?? i} className="flex items-center gap-3">
                    <span className="text-[10px] font-bold text-slate-300 w-4 tabular-nums">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-700 truncate">
                        {c.name || c.company || c.contractor_id || "Unknown"}
                      </p>
                      <div className="h-1 bg-slate-100 rounded-full overflow-hidden mt-1">
                        <div
                          className="h-full bg-amber-400 rounded-full"
                          style={{
                            width: `${((amount / max) * 100).toFixed(1)}%`,
                          }}
                        />
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-slate-900 tabular-nums shrink-0">
                      {valueFormatter(amount)}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {summary?.by_billing_entity &&
        Object.keys(summary.by_billing_entity).length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm mb-6">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">
              By Billing Entity
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {Object.entries(summary.by_billing_entity).map(
                ([entity, data]) => (
                  <div
                    key={entity}
                    className="p-3 bg-slate-50 rounded-lg border border-slate-100"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Building2 className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-sm font-semibold text-slate-800">
                        {entity}
                      </span>
                    </div>
                    <div className="space-y-0.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-500">Revenue</span>
                        <span className="font-mono tabular-nums">
                          ${(data.total ?? 0).toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Txns</span>
                        <span className="font-mono tabular-nums">
                          {data.count}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        )}

      <ViewToolbar
        controller={view}
        columns={columns}
        data={withdrawals}
        resultCount={processedWithdrawals.length}
        className="mb-3"
        actions={
          <button
            onClick={selectAllUninvoiced}
            className="text-xs text-amber-500 hover:text-amber-600 font-medium"
          >
            Select All Uninvoiced
          </button>
        }
      />

      {selectedIds.size > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold text-amber-700">
            {selectedIds.size} selected
          </span>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
            >
              Clear
            </Button>
            {selectedUninvoicedIds.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCreateInvoiceModalOpen(true)}
                className="gap-1"
              >
                <FileText className="w-3.5 h-3.5" />
                Create Invoice ({selectedUninvoicedIds.length})
              </Button>
            )}
          </div>
        </div>
      )}

      <CreateInvoiceModal
        open={createInvoiceModalOpen}
        onOpenChange={setCreateInvoiceModalOpen}
        onCreated={() => {
          setSelectedIds(new Set());
        }}
        preselectedIds={selectedUninvoicedIds}
      />

      <DataTable
        data={processedWithdrawals}
        columns={view.visibleColumns}
        title="Transactions"
        emptyMessage="No transactions found"
        exportable
        exportFilename={`financials-${format(new Date(), "yyyyMMdd")}.csv`}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        isSelectable={(row) => !row.invoice_id}
        onRowClick={(row) => setDetailWithdrawalId(row.id)}
        disableSort
      />

      <WithdrawalDetailPanel
        withdrawalId={detailWithdrawalId}
        open={!!detailWithdrawalId}
        onOpenChange={(open) => !open && setDetailWithdrawalId(null)}
        onViewInvoice={(invoiceId) => {
          setDetailWithdrawalId(null);
          setDetailInvoiceId(invoiceId);
        }}
        onViewJob={(jobId) => {
          setDetailWithdrawalId(null);
          setDetailJobId(jobId);
        }}
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
    </div>
  );
};

export default Financials;
