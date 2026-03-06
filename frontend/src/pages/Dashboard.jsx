import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import {
  AlertTriangle,
  ArrowRight,
  Truck,
  ClipboardList,
  FileText,
  ShoppingCart,
  Package,
} from "lucide-react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { ROLES, ADMIN_ROLES, DATE_PRESETS } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatCard } from "@/components/StatCard";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { TransactionsTable } from "@/components/TransactionsTable";
import { useDashboardStats } from "@/hooks/useDashboard";
import { useReportTrends } from "@/hooks/useReports";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { Panel, SectionHead } from "@/components/Panel";
import { ActivityHeatmap } from "@/components/charts/ActivityHeatmap";
import { ChartExplainer } from "@/components/charts/ChartExplainer";
import api from "@/lib/api-client";

const POSummaryStrip = ({ summary = {} }) => {
  const statuses = [
    { key: "ordered", label: "Ordered", color: "bg-muted-foreground/40" },
    { key: "partial", label: "Partial", color: "bg-muted-foreground/60" },
    { key: "received", label: "Received", color: "bg-muted-foreground/80" },
  ];
  const total = Object.values(summary).reduce((s, v) => s + (v?.total || 0), 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 rounded-full overflow-hidden gap-px mb-2">
        {statuses.map((s) => {
          const val = summary[s.key]?.total || 0;
          if (!val) return null;
          return <div key={s.key} className={s.color} style={{ width: `${(val / total) * 100}%` }} title={`${s.label}: ${valueFormatter(val)}`} />;
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
              <span className="text-[10px] text-muted-foreground tabular-nums">({valueFormatter(v.total)})</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Dashboard = () => {
  const { user } = useAuth();

  const defaultRange = DATE_PRESETS[1].getValue();
  const [dateRange, setDateRange] = useState(defaultRange);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);

  const statsParams = useMemo(() => {
    const p = {};
    if (dateRange.from) p.start_date = dateToISO(dateRange.from);
    if (dateRange.to) p.end_date = endOfDayISO(dateRange.to);
    return p;
  }, [dateRange]);

  const { data: stats, isLoading } = useDashboardStats(statsParams);

  const { data: pendingRequests } = useQuery({
    queryKey: ["materialRequests", "pending-count"],
    queryFn: () => api.materialRequests.list({ status: "pending" }).then((r) => r.length),
    staleTime: 30_000,
  });

  const trailing365 = useMemo(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 365);
    return { start_date: start.toISOString(), end_date: end.toISOString(), group_by: "day" };
  }, []);
  const { data: heatmapTrends } = useReportTrends(trailing365);
  const heatmapData = useMemo(() => {
    if (!heatmapTrends?.series) return [];
    return heatmapTrends.series.map((d) => ({
      date: d.date,
      value: d.transaction_count || 0,
      revenue: d.revenue || 0,
    }));
  }, [heatmapTrends]);

  const isContractor = user?.role === ROLES.CONTRACTOR;

  const rangeLabel = dateRange.from
    ? dateRange.to
      ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}`
      : format(dateRange.from, "MMM d, yyyy")
    : "All time";

  if (isLoading) return <PageSkeleton />;

  if (isContractor) {
    return (
      <div className="p-8" data-testid="dashboard-page">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-semibold text-foreground tracking-tight">Dashboard</h1>
            <p className="text-muted-foreground mt-1 text-sm">Welcome back, {user?.name} · {user?.company || "Independent"}</p>
          </div>
          <DateRangeFilter value={dateRange} onChange={setDateRange} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard label="Total Withdrawals" value={stats?.total_withdrawals || 0} />
          <StatCard label="Total Value" value={valueFormatter(stats?.total_spent || 0)} accent="emerald" />
          <StatCard label="Uninvoiced" value={valueFormatter(stats?.unpaid_balance || 0)} accent="amber" />
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
                      <span className="font-semibold text-foreground tabular-nums">${w.total?.toFixed(2)}</span>
                      <StatusBadge status={w.invoice_id ? "invoiced" : "uninvoiced"} />
                    </div>
                  </div>
                  {w.items?.length > 0 && (
                    <div className="space-y-1 mt-2 border-t border-border/50 pt-2">
                      {w.items.map((item, j) => (
                        <div key={j} className="flex items-center justify-between text-xs text-muted-foreground">
                          <span className="truncate max-w-[200px]">{item.name || item.product_name || "Item"}</span>
                          <span className="tabular-nums text-muted-foreground">{item.quantity} × ${(item.unit_price ?? 0).toFixed(2)}</span>
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
  const openPOCount = (stats?.po_summary?.ordered?.count || 0) + (stats?.po_summary?.partial?.count || 0);

  return (
    <div className="p-8" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1 text-sm">{rangeLabel}</p>
        </div>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      {/* ── Alerts ── */}
      {(stats?.low_stock_count > 0 || (pendingRequests ?? 0) > 0) && (
        <div className="flex flex-wrap gap-2 mb-6">
          {(pendingRequests ?? 0) > 0 && (
            <Link to="/pending-requests" className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-info/10 border border-info/30 text-info hover:bg-info/15 text-sm">
              <ClipboardList className="w-4 h-4" />
              <span>{pendingRequests} pending requests</span>
              <ArrowRight className="w-3.5 h-3.5 text-info" />
            </Link>
          )}
          {stats?.low_stock_count > 0 && (
            <Link to="/inventory?low_stock=1" className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-muted border border-border text-foreground hover:bg-muted text-sm">
              <AlertTriangle className="w-4 h-4 text-accent" />
              <span>{stats.low_stock_count} items low on stock</span>
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
            </Link>
          )}
        </div>
      )}

      {/* ── Operational KPI cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Pending Requests" value={pendingRequests ?? 0} icon={ClipboardList} accent="blue" note={pendingRequests > 0 ? "awaiting processing" : "all clear"} />
        <StatCard label="Low Stock Alerts" value={stats?.low_stock_count || 0} icon={Package} accent={stats?.low_stock_count > 0 ? "amber" : "slate"} note={`${stats?.inventory_units || 0} total units`} />
        <StatCard label="Uninvoiced" value={valueFormatter(stats?.unpaid_total || 0)} icon={FileText} accent={stats?.unpaid_total > 0 ? "amber" : "slate"} note={`${stats?.range_transactions || 0} transactions`} />
        <StatCard label="Open POs" value={openPOCount} icon={Truck} accent={openPOCount > 0 ? "violet" : "slate"} note={hasPOs ? valueFormatter((stats?.po_summary?.ordered?.total || 0) + (stats?.po_summary?.partial?.total || 0)) + " in progress" : "none in progress"} />
      </div>

      {/* ── Activity Heatmap ── */}
      {heatmapData.length > 0 && (
        <Panel className="mb-6">
          <SectionHead title="Transaction Activity" action={
            <span className="text-xs text-muted-foreground tabular-nums">{heatmapData.reduce((s, d) => s + d.value, 0).toLocaleString()} total</span>
          } />
          <ChartExplainer
            title="Activity Heatmap"
            bullets={[
              "Each square is one day — darker = more transactions",
              "Rows are days of the week (Mon–Sun), columns are weeks",
              "Hover over any square to see the exact count and revenue",
              "Look for patterns: busy days, quiet weeks, or seasonal trends",
            ]}
          >
            <ActivityHeatmap
              data={heatmapData}
              label="transactions"
              tooltipExtra={(d) => d?.revenue ? `Revenue: $${d.revenue.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : ""}
            />
          </ChartExplainer>
        </Panel>
      )}

      {/* ── PO Activity + Low Stock ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {hasPOs && (
          <Panel>
            <SectionHead title="Purchase orders" action={
              <Link to="/purchase-orders" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                All POs <Truck className="w-3 h-3" />
              </Link>
            } />
            <div className="mb-4">
              <span className="text-lg font-bold text-foreground tabular-nums">{openPOCount} open</span>
              <span className="text-xs text-muted-foreground ml-2">purchase orders</span>
            </div>
            <POSummaryStrip summary={stats.po_summary} />
          </Panel>
        )}

        {stats?.low_stock_alerts?.length > 0 && (
          <Panel>
            <SectionHead title="Low stock items" action={
              <Link to="/inventory?low_stock=1" className="text-xs text-muted-foreground hover:text-foreground">
                {stats.low_stock_count} items →
              </Link>
            } />
            <div className="space-y-2 max-h-[260px] overflow-auto -mx-6 px-6">
              {stats.low_stock_alerts.map((product, i) => (
                <Link key={product.id || i} to="/inventory" className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted">
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

      {/* ── Transactions Table ── */}
      {ADMIN_ROLES.includes(user?.role) && <TransactionsTable dateParams={statsParams} />}

      {ADMIN_ROLES.includes(user?.role) && (
        <StockHistoryModal product={stockHistoryProduct} open={!!stockHistoryProduct} onOpenChange={(open) => !open && setStockHistoryProduct(null)} />
      )}
    </div>
  );
};

export default Dashboard;
