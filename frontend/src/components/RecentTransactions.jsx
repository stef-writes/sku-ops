import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ExternalLink, Filter, X } from "lucide-react";
import { format } from "date-fns";
import { Button } from "@/components/ui/button";
import api from "@/lib/api-client";
import { dashboardKeys } from "@/hooks/useDashboard";

const PAYMENT_STATUSES = [
  { value: "", label: "All statuses" },
  { value: "unpaid", label: "Unpaid" },
  { value: "invoiced", label: "Invoiced" },
  { value: "paid", label: "Paid" },
];

function dateToISO(d) {
  if (!d) return undefined;
  const dt = new Date(d);
  dt.setHours(0, 0, 0, 0);
  return dt.toISOString();
}

function endOfDayISO(d) {
  if (!d) return undefined;
  const dt = new Date(d);
  dt.setHours(23, 59, 59, 999);
  return dt.toISOString();
}

export function RecentTransactions({ dateRange, onProductStockHistory }) {
  const [contractorId, setContractorId] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [allRows, setAllRows] = useState([]);

  const { data: contractors } = useQuery({
    queryKey: ["contractors"],
    queryFn: () => api.contractors.list(),
    staleTime: 60_000,
  });

  const params = useMemo(() => {
    const p = { limit: 20, offset };
    if (dateRange?.from) p.start_date = dateToISO(dateRange.from);
    if (dateRange?.to) p.end_date = endOfDayISO(dateRange.to);
    if (contractorId) p.contractor_id = contractorId;
    if (paymentStatus) p.payment_status = paymentStatus;
    return p;
  }, [dateRange, contractorId, paymentStatus, offset]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: dashboardKeys.transactions(params),
    queryFn: () => api.dashboard.transactions(params),
    keepPreviousData: true,
  });

  useEffect(() => {
    if (!data) return;
    setAllRows((prev) => (offset === 0 ? data.withdrawals : [...prev, ...data.withdrawals]));
  }, [data, offset]);

  useEffect(() => {
    setOffset(0);
    setAllRows([]);
  }, [dateRange, contractorId, paymentStatus]);

  const hasMore = data?.has_more ?? false;
  const activeFilterCount = (contractorId ? 1 : 0) + (paymentStatus ? 1 : 0);

  const clearFilters = () => {
    setContractorId("");
    setPaymentStatus("");
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

        <select
          value={contractorId}
          onChange={(e) => setContractorId(e.target.value)}
          className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-orange-200 focus:border-orange-400"
        >
          <option value="">All contractors</option>
          {(contractors || []).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        <select
          value={paymentStatus}
          onChange={(e) => setPaymentStatus(e.target.value)}
          className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-orange-200 focus:border-orange-400"
        >
          {PAYMENT_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>

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

function WithdrawalBlock({ withdrawal: w, onProductStockHistory }) {
  const statusClasses = {
    paid: "bg-emerald-100 text-emerald-700",
    invoiced: "bg-blue-100 text-blue-700",
    unpaid: "bg-amber-100 text-amber-700",
  };

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden bg-white">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-100">
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
          <span
            className={`text-xs px-2 py-0.5 rounded font-medium ${
              statusClasses[w.payment_status] || statusClasses.unpaid
            }`}
          >
            {w.payment_status}
          </span>
        </div>
      </div>

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
