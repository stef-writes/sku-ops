import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ExternalLink, Filter, X } from "lucide-react";
import { format } from "date-fns";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/lib/api-client";
import { keys } from "@/hooks/queryKeys";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { useContractors } from "@/hooks/useContractors";

export function RecentTransactions({ dateRange, onProductStockHistory, onWithdrawalClick }) {
  const [contractorId, setContractorId] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [allRows, setAllRows] = useState([]);

  const { data: contractors } = useContractors();

  const params = useMemo(() => {
    const p = { limit: 20, offset };
    if (dateRange?.from) p.start_date = dateToISO(dateRange.from);
    if (dateRange?.to) p.end_date = endOfDayISO(dateRange.to);
    if (contractorId) p.contractor_id = contractorId;
    if (invoiceStatus) p.payment_status = invoiceStatus;
    return p;
  }, [dateRange, contractorId, invoiceStatus, offset]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: keys.dashboard.transactions(params),
    queryFn: () => api.dashboard.transactions(params),
    keepPreviousData: true,
  });

  useEffect(() => {
    if (!data) return;
    setAllRows((prev) => (offset === 0 ? (data.withdrawals || []) : [...prev, ...(data.withdrawals || [])]));
  }, [data, offset]);

  useEffect(() => {
    setOffset(0);
    setAllRows([]);
  }, [dateRange, contractorId, invoiceStatus]);

  const hasMore = data?.has_more ?? false;
  const activeFilterCount = (contractorId ? 1 : 0) + (invoiceStatus ? 1 : 0);

  const clearFilters = () => {
    setContractorId("");
    setInvoiceStatus("");
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mb-6 shadow-sm" data-testid="recent-transactions-terminal">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-200">
        <h2 className="text-lg font-semibold text-slate-900">Recent Transactions</h2>
        <Link
          to="/financials"
          className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1"
        >
          View all <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Filter className="w-3.5 h-3.5" />
          <span className="text-xs font-medium uppercase tracking-wide">Filter</span>
        </div>

        <Select value={contractorId || "all"} onValueChange={(v) => setContractorId(v === "all" ? "" : v)}>
          <SelectTrigger className="h-8 w-[160px]"><SelectValue placeholder="All contractors" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All contractors</SelectItem>
            {(contractors || []).map((c) => (
              <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={invoiceStatus || "all"} onValueChange={(v) => setInvoiceStatus(v === "all" ? "" : v)}>
          <SelectTrigger className="h-8 w-[140px]"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="unpaid">Uninvoiced</SelectItem>
            <SelectItem value="invoiced">Invoiced</SelectItem>
          </SelectContent>
        </Select>

        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={clearFilters}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
          >
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      {isLoading && allRows.length === 0 ? (
        <div className="rounded-xl bg-slate-50/80 border border-slate-200 p-8 text-center text-slate-500 text-sm">
          Loading…
        </div>
      ) : allRows.length === 0 ? (
        <div className="rounded-xl bg-slate-50/80 border border-slate-200 p-8 text-center text-slate-500 text-sm">
          No transactions match these filters
        </div>
      ) : (
        <>
          <div
            className="rounded-xl border border-slate-200 overflow-y-auto overflow-x-hidden bg-slate-50/50 p-2 space-y-3"
            style={{ maxHeight: 360 }}
          >
            {allRows.map((w) => (
              <WithdrawalBlock
                key={w.id}
                withdrawal={w}
                onProductStockHistory={onProductStockHistory}
                onClick={() => onWithdrawalClick?.(w.id)}
              />
            ))}
          </div>
          {hasMore && (
            <Button
              variant="outline"
              size="sm"
              className="mt-3 w-full"
              onClick={() => setOffset(allRows.length)}
              disabled={isFetching}
            >
              {isFetching ? "Loading…" : "Load more"}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function WithdrawalBlock({ withdrawal: w, onProductStockHistory, onClick }) {
  const isInvoiced = !!w.invoice_id;
  const statusClass = isInvoiced
    ? "bg-blue-100 text-blue-700"
    : "bg-amber-100 text-amber-700";
  const statusLabel = isInvoiced ? "invoiced" : "uninvoiced";

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden bg-white hover:border-slate-300 transition-colors">
      <button
        type="button"
        onClick={onClick}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-100 hover:bg-slate-100 transition-colors text-left cursor-pointer"
      >
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-slate-800 font-semibold truncate">
            {w.contractor_name || "—"}
          </span>
          <span className="text-slate-500 text-xs">
            {format(new Date(w.created_at), "MMM d, h:mm a")} · Job {w.job_id || "—"}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-lg font-bold text-slate-900 tabular-nums">
            ${(w.total || 0).toFixed(2)}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded font-medium ${statusClass}`}>
            {statusLabel}
          </span>
        </div>
      </button>

      <ul className="divide-y divide-slate-100">
        {(w.items || []).map((item, j) => (
          <WithdrawalItem
            key={`${w.id}-${j}`}
            item={item}
            onProductStockHistory={onProductStockHistory}
          />
        ))}
      </ul>
    </div>
  );
}

function WithdrawalItem({ item, onProductStockHistory }) {
  const unitLabel = item.unit && item.unit !== "each" ? ` ${item.unit}` : "";
  const priceStr =
    item.quantity === 1 && !unitLabel
      ? `$${(item.subtotal || 0).toFixed(2)}`
      : `${item.quantity}${unitLabel} @ $${(item.price || 0).toFixed(2)}`;

  return (
    <li className="flex items-center justify-between gap-4 px-4 py-2 pl-6 group">
      <button
        type="button"
        onClick={() =>
          item.product_id &&
          onProductStockHistory?.({ id: item.product_id, sku: item.sku, name: item.name })
        }
        className="truncate text-left text-slate-700 hover:text-slate-900 text-sm flex-1 min-w-0"
        title="View stock history"
      >
        {item.name || item.sku}
      </button>
      <span className="shrink-0 flex items-center gap-2">
        <span className="text-slate-500 text-sm tabular-nums">{priceStr}</span>
        {item.product_id && (
          <Link
            to={`/inventory?search=${encodeURIComponent(item.sku || "")}`}
            className="p-1 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-50 transition-colors opacity-60 hover:opacity-100"
            title="Inventory"
          >
            <ExternalLink className="w-3 h-3" />
          </Link>
        )}
      </span>
    </li>
  );
}
