import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import { AlertTriangle, Truck, ClipboardList, ShoppingCart, Package, HardHat } from "lucide-react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { ROLES, DATE_PRESETS } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { QueryError } from "@/components/QueryError";
import { StatCard } from "@/components/StatCard";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { RecentTransactions } from "@/components/RecentTransactions";
import { ActionTile } from "@/components/ActionTile";
import { useDashboardStats } from "@/hooks/useDashboard";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { Panel, SectionHead } from "@/components/Panel";
import { keys } from "@/hooks/queryKeys";

const POSummaryStrip = ({ summary = {} }) => {
  const statuses = [
    { key: "ordered", label: "On Order", color: "bg-muted-foreground/40" },
    { key: "partial", label: "At Dock", color: "bg-muted-foreground/60" },
    { key: "received", label: "Received", color: "bg-muted-foreground/80" },
  ];
  const total = Object.values(summary).reduce((s, v) => s + (v?.total || 0), 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 rounded-full overflow-hidden gap-px mb-2">
        {statuses.map((s) => {
          const val = summary[s.key]?.total || 0;
          if (!val) return null;
          return (
            <div
              key={s.key}
              className={s.color}
              style={{ width: `${(val / total) * 100}%` }}
              title={`${s.label}: ${valueFormatter(val)}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {statuses.map((s) => {
          const v = summary[s.key];
          if (!v) return null;
          return (
            <div key={s.key} className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${s.color}`} />
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <span className="text-xs font-bold text-foreground tabular-nums">{v.count}</span>
              <span className="text-[10px] text-muted-foreground tabular-nums">
                ({valueFormatter(v.total)})
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Dashboard = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const defaultRange = DATE_PRESETS[1].getValue();
  const [dateRange, setDateRange] = useState(defaultRange);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);

  const statsParams = useMemo(() => {
    const p = {};
    if (dateRange.from) p.start_date = dateToISO(dateRange.from);
    if (dateRange.to) p.end_date = endOfDayISO(dateRange.to);
    return p;
  }, [dateRange]);

  const { data: stats, isLoading, isError, error, refetch } = useDashboardStats(statsParams);

  // Derive pending-request count from the materialRequests cache so it stays
  // in sync with the real-time invalidations on keys.materialRequests.all.
  const pendingRequests = useMemo(() => {
    const cached = queryClient.getQueriesData({
      queryKey: keys.materialRequests.all,
    });
    for (const [, data] of cached) {
      if (Array.isArray(data)) {
        const pending = data.filter((r) => r.status === "pending");
        if (pending.length > 0 || data.length > 0) return pending.length;
      }
    }
    return stats?.pending_requests_count ?? 0;
  }, [queryClient, stats]);

  const isContractor = user?.role === ROLES.CONTRACTOR;

  const rangeLabel = dateRange.from
    ? dateRange.to
      ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}`
      : format(dateRange.from, "MMM d, yyyy")
    : "All time";

  if (isLoading) return <PageSkeleton />;
  if (isError) return <QueryError error={error} onRetry={refetch} />;

  if (isContractor) {
    return (
      <div className="p-8" data-testid="dashboard-page">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-semibold text-foreground tracking-tight">Dashboard</h1>
            <p className="text-muted-foreground mt-1 text-sm">
              Welcome back, {user?.name} · {user?.company || "Independent"}
            </p>
          </div>
          <DateRangeFilter value={dateRange} onChange={setDateRange} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard label="Total Withdrawals" value={stats?.total_withdrawals || 0} />
          <StatCard
            label="Total Value"
            value={valueFormatter(stats?.total_spent || 0)}
            accent="emerald"
          />
          <StatCard
            label="Uninvoiced"
            value={valueFormatter(stats?.unpaid_balance || 0)}
            accent="amber"
          />
        </div>

        <Panel>
          <h2 className="text-base font-semibold text-foreground mb-4">Recent Withdrawals</h2>
          {stats?.recent_withdrawals?.length > 0 ? (
            <div className="space-y-2">
              {stats.recent_withdrawals.map((w, i) => (
                <div key={w.id || i} className="p-4 bg-muted/80 rounded-lg border border-border/50">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-mono text-xs text-muted-foreground">Job: {w.job_id}</p>
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-foreground tabular-nums">
                        ${w.total?.toFixed(2)}
                      </span>
                      <StatusBadge status={w.invoice_id ? "invoiced" : "uninvoiced"} />
                    </div>
                  </div>
                  {w.items?.length > 0 && (
                    <div className="space-y-1 mt-2 border-t border-border/50 pt-2">
                      {w.items.map((item, j) => (
                        <div
                          key={j}
                          className="flex items-center justify-between text-xs text-muted-foreground"
                        >
                          <span className="truncate max-w-[200px]">
                            {item.name || item.product_name || "Item"}
                          </span>
                          <span className="tabular-nums text-muted-foreground">
                            {item.quantity} × ${(item.unit_price ?? 0).toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <ShoppingCart className="w-10 h-10 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No withdrawals in this range</p>
            </div>
          )}
        </Panel>
      </div>
    );
  }

  const hasPOs = stats?.po_summary && Object.keys(stats.po_summary).length > 0;
  const orderedPOCount = stats?.po_summary?.ordered?.count || 0;
  const partialPOCount = stats?.po_summary?.partial?.count || 0;
  const receivedPOCount = stats?.po_summary?.received?.count || 0;
  const openPOCount = orderedPOCount + partialPOCount;

  return (
    <div className="p-8" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Daily yard activity, inbound deliveries, and contractor work · {rangeLabel}
          </p>
        </div>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-foreground">Quick actions</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <ActionTile
            to="/pending-requests"
            icon={ClipboardList}
            title="Review requests"
            description="Process contractor requests waiting for issue."
          />
          <ActionTile
            to="/pos"
            icon={ShoppingCart}
            title="Issue materials"
            description="Create a new material issue for a contractor."
          />
          <ActionTile
            to="/import"
            icon={Truck}
            title="Receive delivery"
            description="Review inbound documents and receive stock into inventory."
          />
          <ActionTile
            to="/purchase-orders"
            icon={Package}
            title="Open purchase orders"
            description="Track vendor deliveries and what's still on order."
          />
        </div>
      </div>

      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-foreground">Work queues</h2>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Pending Requests"
            value={pendingRequests ?? 0}
            icon={ClipboardList}
            accent="blue"
            note={pendingRequests > 0 ? "awaiting processing" : "all clear"}
            href="/pending-requests"
          />
          <StatCard
            label="Awaiting Delivery"
            value={orderedPOCount}
            icon={Truck}
            accent={orderedPOCount > 0 ? "violet" : "slate"}
            note={
              orderedPOCount > 0
                ? `${valueFormatter(stats?.po_summary?.ordered?.total || 0)} on order`
                : "no inbound orders"
            }
            href="/purchase-orders"
          />
          <StatCard
            label="At Dock"
            value={partialPOCount}
            icon={Package}
            accent={partialPOCount > 0 ? "orange" : "slate"}
            note={partialPOCount > 0 ? "ready to receive into stock" : "nothing at dock"}
            href="/purchase-orders"
          />
          <StatCard
            label="Low Stock Alerts"
            value={stats?.low_stock_count || 0}
            icon={AlertTriangle}
            accent={stats?.low_stock_count > 0 ? "amber" : "slate"}
            note={`${stats?.total_products || 0} SKUs · ${stats?.inventory_units || 0} units on hand`}
            href="/inventory?low_stock=1"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
        <StatCard
          label="Inventory Value"
          value={valueFormatter(stats?.inventory_retail || 0)}
          icon={Package}
          accent="emerald"
          note={`${valueFormatter(stats?.inventory_cost || 0)} cost basis`}
          href="/inventory"
        />
        <StatCard
          label="Received This Period"
          value={receivedPOCount}
          icon={Package}
          accent={receivedPOCount > 0 ? "emerald" : "slate"}
          note={
            receivedPOCount > 0
              ? `${valueFormatter(stats?.po_summary?.received?.total || 0)} received`
              : "no completed receipts"
          }
          href="/purchase-orders"
        />
        <StatCard
          label="Contractors"
          value={stats?.total_contractors || 0}
          icon={HardHat}
          accent="slate"
          note={`${stats?.total_vendors || 0} vendors in network`}
          href="/contractors"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {hasPOs && (
          <Panel>
            <SectionHead
              title="Inbound delivery status"
              action={
                <Link
                  to="/purchase-orders"
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  All POs <Truck className="w-3 h-3" />
                </Link>
              }
            />
            <div className="mb-4 flex flex-wrap items-end gap-4">
              <div>
                <span className="text-lg font-bold text-foreground tabular-nums">
                  {openPOCount}
                </span>
                <span className="text-xs text-muted-foreground ml-2">still inbound</span>
              </div>
              <div className="text-xs text-muted-foreground">
                {orderedPOCount} on order · {partialPOCount} at dock · {receivedPOCount} received
              </div>
            </div>
            <POSummaryStrip summary={stats.po_summary} />
          </Panel>
        )}

        {stats?.low_stock_alerts?.length > 0 && (
          <Panel>
            <SectionHead
              title="Low stock items"
              action={
                <Link
                  to="/inventory?low_stock=1"
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {stats.low_stock_count} items →
                </Link>
              }
            />
            <div className="space-y-2 max-h-[260px] overflow-auto -mx-6 px-6">
              {stats.low_stock_alerts.map((product, i) => (
                <Link
                  key={product.id || i}
                  to="/inventory"
                  className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted"
                >
                  <div>
                    <p className="font-mono text-xs text-muted-foreground">{product.sku}</p>
                    <p className="text-sm text-foreground truncate max-w-[200px]">{product.name}</p>
                  </div>
                  <div className="flex items-center gap-3 text-right shrink-0 text-xs text-muted-foreground">
                    <span>{product.quantity} left</span>
                    <span className="text-muted-foreground">min {product.min_stock}</span>
                  </div>
                </Link>
              ))}
            </div>
          </Panel>
        )}
      </div>

      <RecentTransactions
        dateRange={dateRange}
        onProductStockHistory={setStockHistoryProduct}
        title="Recent material activity"
        viewAllHref="/reports?tab=operations"
        viewAllLabel="Operations view"
      />

      {!isContractor && (
        <StockHistoryModal
          product={stockHistoryProduct}
          open={!!stockHistoryProduct}
          onOpenChange={(open) => !open && setStockHistoryProduct(null)}
        />
      )}
    </div>
  );
};

export default Dashboard;
