import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  DollarSign,
  ShoppingCart,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Warehouse,
  TrendingUp,
  Truck,
} from "lucide-react";
import { AreaChart } from "@tremor/react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { ROLES, ADMIN_ROLES, DATE_PRESETS } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatCard } from "@/components/StatCard";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { RecentTransactions } from "@/components/RecentTransactions";
import { WithdrawalDetailPanel } from "@/components/WithdrawalDetailPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { useDashboardStats } from "@/hooks/useDashboard";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { Panel, SectionHead } from "@/components/Panel";

const DeptMarginBars = ({ data = [] }) => {
  const max = useMemo(() => Math.max(...data.map((d) => Math.max(d.revenue, d.cost)), 1), [data]);
  return (
    <div className="space-y-3">
      {data.slice(0, 8).map((d) => (
          <div key={d.department}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-slate-700 truncate">{d.department}</span>
              <div className="flex items-center gap-3 text-xs tabular-nums shrink-0 text-slate-500">
                <span>{d.margin_pct}%</span>
                <span>{valueFormatter(d.profit)}</span>
              </div>
            </div>
            <div className="relative h-4 bg-slate-100 rounded-md overflow-hidden">
              <div className="absolute left-0 top-0 h-full bg-slate-200 rounded-md transition-all duration-500" style={{ width: `${(d.revenue / max) * 100}%` }} />
              <div className="absolute left-0 top-0 h-full bg-orange-300/80 rounded-md transition-all duration-500" style={{ width: `${(d.cost / max) * 100}%` }} />
            </div>
          </div>
      ))}
      <div className="flex items-center gap-4 pt-1 text-[10px] text-slate-400">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-orange-300/80 inline-block" />Cost</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-slate-200 inline-block" />Revenue</span>
      </div>
    </div>
  );
};

const POSummaryStrip = ({ summary = {} }) => {
  const statuses = [
    { key: "ordered", label: "Ordered", color: "bg-slate-300" },
    { key: "partial", label: "Partial", color: "bg-slate-400" },
    { key: "received", label: "Received", color: "bg-slate-500" },
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
              <span className="text-xs text-slate-500">{s.label}</span>
              <span className="text-xs font-bold text-slate-700 tabular-nums">{v.count}</span>
              <span className="text-[10px] text-slate-400 tabular-nums">({valueFormatter(v.total)})</span>
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
  const [detailWithdrawalId, setDetailWithdrawalId] = useState(null);

  const statsParams = useMemo(() => {
    const p = {};
    if (dateRange.from) p.start_date = dateToISO(dateRange.from);
    if (dateRange.to) p.end_date = endOfDayISO(dateRange.to);
    return p;
  }, [dateRange]);

  const { data: stats, isLoading } = useDashboardStats(statsParams);

  const isContractor = user?.role === ROLES.CONTRACTOR;
  const isAdmin = user?.role === ROLES.ADMIN;

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
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Dashboard</h1>
            <p className="text-slate-500 mt-1 text-sm">Welcome back, {user?.name} · {user?.company || "Independent"}</p>
          </div>
          <DateRangeFilter value={dateRange} onChange={setDateRange} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard label="Total Withdrawals" value={stats?.total_withdrawals || 0} />
          <StatCard label="Total Value" value={valueFormatter(stats?.total_spent || 0)} accent="emerald" />
          <StatCard label="Uninvoiced" value={valueFormatter(stats?.unpaid_balance || 0)} accent="amber" />
        </div>

        <Panel>
          <h2 className="text-base font-semibold text-slate-900 mb-4">Recent Withdrawals</h2>
          {stats?.recent_withdrawals?.length > 0 ? (
            <div className="space-y-2">
              {stats.recent_withdrawals.map((w, i) => (
                <div key={w.id || i} className="flex items-center justify-between p-4 bg-slate-50/80 rounded-lg border border-slate-100">
                  <div>
                    <p className="font-mono text-xs text-slate-400">Job: {w.job_id}</p>
                    <p className="text-sm text-slate-600 mt-0.5">{w.items?.length || 0} items</p>
                  </div>
                  <div className="text-right flex items-center gap-3">
                    <span className="font-semibold text-slate-900 tabular-nums">${w.total?.toFixed(2)}</span>
                    <StatusBadge status={w.invoice_id ? "invoiced" : "uninvoiced"} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              <ShoppingCart className="w-10 h-10 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No withdrawals in this range</p>
            </div>
          )}
        </Panel>
      </div>
    );
  }

  const dailyChartData = stats?.revenue_by_day?.length
    ? stats.revenue_by_day.map((d) => ({
        date: format(new Date(d.date), "MMM d"),
        Revenue: d.revenue,
        Cost: d.cost || 0,
        Profit: d.profit || 0,
      }))
    : [];

  const inventoryCost = stats?.inventory_cost || 0;

  const hasPOs = stats?.po_summary && Object.keys(stats.po_summary).length > 0;
  const openPOTotal = (stats?.po_summary?.ordered?.total || 0) + (stats?.po_summary?.partial?.total || 0);

  return (
    <div className="p-8" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Dashboard</h1>
          <p className="text-slate-500 mt-1 text-sm">{rangeLabel}</p>
        </div>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      {/* ── Alerts ── */}
      {stats?.low_stock_count > 0 && (
        <div className="flex flex-wrap gap-2 mb-6">
          <Link to="/inventory?low_stock=1" className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100 text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>{stats.low_stock_count} items low on stock</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
          </Link>
        </div>
      )}

      {/* ── Row 1: Key metrics ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Stock on Hand" value={valueFormatter(inventoryCost)} icon={Warehouse} accent="slate" note={`${stats?.inventory_units || 0} units at cost`} />

        <StatCard label="Withdrawals (cost)" value={valueFormatter(stats?.range_cogs || 0)} icon={DollarSign} accent="orange" note={`${stats?.range_transactions || 0} withdrawals this period`} />

        <StatCard label="Profit (this period)" value={valueFormatter(stats?.range_gross_profit || 0)} icon={TrendingUp} accent={stats?.range_margin_pct >= 30 ? "emerald" : "orange"} note={`${stats?.range_margin_pct || 0}% margin`} />

        <StatCard label="Uninvoiced" value={valueFormatter(stats?.unpaid_total || 0)} icon={DollarSign} accent={stats?.unpaid_total > 0 ? "amber" : "slate"} note={`${stats?.low_stock_count || 0} items low stock`} />
      </div>

      {/* ── Row 2: Chart + Department Margins ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-6">
        <Panel className="lg:col-span-3">
          <SectionHead title={`Revenue & cost — ${rangeLabel}`} action={
            <Link to="/reports" className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1">
              Full Reports <BarChart3 className="w-3 h-3" />
            </Link>
          } />
          {dailyChartData.length > 0 ? (
            <AreaChart
              data={dailyChartData}
              index="date"
              categories={["Cost", "Revenue", "Profit"]}
              colors={["orange", "slate", "emerald"]}
              valueFormatter={valueFormatter}
              showLegend
              className="h-52"
              curveType="monotone"
            />
          ) : (
            <div className="h-52 flex items-center justify-center text-sm text-slate-300">No data for this period</div>
          )}
        </Panel>

        <Panel className="lg:col-span-2">
          <SectionHead title="Profit by department" />
          {stats?.dept_margins?.length > 0 ? (
            <DeptMarginBars data={stats.dept_margins} />
          ) : (
            <div className="h-52 flex items-center justify-center text-sm text-slate-300">No department data</div>
          )}
        </Panel>
      </div>

      {/* ── Row 3: PO Activity + Low Stock ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {hasPOs && (
          <Panel>
            <SectionHead title="Purchase orders" action={
              <Link to="/purchase-orders" className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1">
                All POs <Truck className="w-3 h-3" />
              </Link>
            } />
            <div className="mb-4">
              <span className="text-lg font-bold text-slate-900 tabular-nums">{valueFormatter(openPOTotal)}</span>
              <span className="text-xs text-slate-400 ml-2">in progress</span>
            </div>
            <POSummaryStrip summary={stats.po_summary} />
          </Panel>
        )}

        {stats?.low_stock_alerts?.length > 0 && (
          <Panel>
            <SectionHead title="Low stock items" action={
              <Link to="/inventory?low_stock=1" className="text-xs text-slate-500 hover:text-slate-700">
                {stats.low_stock_count} items →
              </Link>
            } />
            <div className="space-y-2 max-h-[260px] overflow-auto -mx-6 px-6">
              {stats.low_stock_alerts.map((product, i) => (
                <Link key={product.id || i} to="/inventory" className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50">
                  <div>
                    <p className="font-mono text-xs text-slate-500">{product.sku}</p>
                    <p className="text-sm text-slate-700 truncate max-w-[200px]">{product.name}</p>
                  </div>
                  <div className="flex items-center gap-3 text-right shrink-0 text-xs text-slate-600">
                    <span>{product.quantity} left</span>
                    <span className="text-slate-400">min {product.min_stock}</span>
                  </div>
                </Link>
              ))}
            </div>
          </Panel>
        )}
      </div>

      {/* ── Row 4: Recent Transactions ── */}
      {ADMIN_ROLES.includes(user?.role) && (
        <RecentTransactions
          dateRange={dateRange}
          onProductStockHistory={setStockHistoryProduct}
          onWithdrawalClick={setDetailWithdrawalId}
        />
      )}

      {ADMIN_ROLES.includes(user?.role) && (
        <StockHistoryModal product={stockHistoryProduct} open={!!stockHistoryProduct} onOpenChange={(open) => !open && setStockHistoryProduct(null)} />
      )}

      <WithdrawalDetailPanel
        withdrawalId={detailWithdrawalId}
        open={!!detailWithdrawalId}
        onOpenChange={(open) => !open && setDetailWithdrawalId(null)}
      />
    </div>
  );
};

export default Dashboard;
