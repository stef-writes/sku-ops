import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {
  DollarSign,
  ShoppingCart,
  Package,
  AlertTriangle,
  ArrowRight,
  BarChart3,
} from "lucide-react";
import { AreaChart } from "@tremor/react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { ROLES, ADMIN_ROLES, DATE_PRESETS } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { RecentTransactions } from "@/components/RecentTransactions";
import { StatusBadge } from "@/components/StatusBadge";
import { DateRangeFilter } from "@/components/DateRangeFilter";
import { useDashboardStats } from "@/hooks/useDashboard";

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

const Dashboard = () => {
  const { user } = useAuth();

  const defaultRange = DATE_PRESETS[1].getValue(); // Last 7 days
  const [dateRange, setDateRange] = useState(defaultRange);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);

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
          <StatCard label="Unpaid Balance" value={valueFormatter(stats?.unpaid_balance || 0)} accent="amber" />
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
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
                    <StatusBadge status={w.payment_status} />
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
        </div>
      </div>
    );
  }

  const revenueChartData = stats?.revenue_by_day?.length
    ? stats.revenue_by_day.map((d) => ({ date: format(new Date(d.date), "MMM d"), Revenue: d.revenue }))
    : [];

  return (
    <div className="p-8" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Dashboard</h1>
          <p className="text-slate-500 mt-1 text-sm">Welcome back, {user?.name}</p>
        </div>
        <DateRangeFilter value={dateRange} onChange={setDateRange} />
      </div>

      {(stats?.low_stock_count > 0 || (isAdmin && stats?.unpaid_total > 0)) && (
        <div className="flex flex-wrap gap-2 mb-6">
          {stats?.low_stock_count > 0 && (
            <Link to="/inventory?low_stock=1" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-amber-50 border border-amber-200 hover:border-amber-400 transition-colors group">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span className="text-sm font-medium text-amber-800">{stats.low_stock_count} items low on stock</span>
              <ArrowRight className="w-3.5 h-3.5 text-amber-400 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          )}
          {isAdmin && stats?.unpaid_total > 0 && (
            <Link to="/financials" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-rose-50 border border-rose-200 hover:border-rose-400 transition-colors group">
              <DollarSign className="w-4 h-4 text-rose-500" />
              <span className="text-sm font-medium text-rose-800">{valueFormatter(stats.unpaid_total)} unpaid</span>
              <ArrowRight className="w-3.5 h-3.5 text-rose-400 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Revenue" value={valueFormatter(stats?.range_revenue || 0)} sub={`${stats?.range_transactions || 0} withdrawals`} accent="emerald" />
        <StatCard label="Unpaid" value={valueFormatter(stats?.unpaid_total || 0)} accent={stats?.unpaid_total > 0 ? "orange" : "slate"} />
        <StatCard label="Total Products" value={stats?.total_products || 0} />
        <StatCard label="Low Stock" value={stats?.low_stock_count || 0} accent={stats?.low_stock_count > 0 ? "amber" : "slate"} />
      </div>

      {revenueChartData.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-slate-900">Revenue — {rangeLabel}</h2>
            <Link to="/reports" className="text-sm text-slate-400 hover:text-slate-600 flex items-center gap-1">
              Reports <BarChart3 className="w-3.5 h-3.5" />
            </Link>
          </div>
          <AreaChart data={revenueChartData} index="date" categories={["Revenue"]} colors={["orange"]} valueFormatter={valueFormatter} showLegend={false} className="h-44" />
        </div>
      )}

      {ADMIN_ROLES.includes(user?.role) && (
        <RecentTransactions dateRange={dateRange} onProductStockHistory={setStockHistoryProduct} />
      )}

      {stats?.low_stock_alerts?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-slate-900">Low Stock Alerts</h2>
            <Link to="/inventory?low_stock=1" className="text-sm text-slate-400 hover:text-slate-600 flex items-center gap-1">
              Inventory <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <div className="space-y-2">
            {stats.low_stock_alerts.map((product, i) => (
              <Link key={product.id || i} to="/inventory" className="flex items-center justify-between p-3 bg-amber-50/60 rounded-lg border border-amber-100 hover:border-amber-200 transition-colors">
                <div>
                  <p className="font-mono text-xs text-amber-600">{product.sku}</p>
                  <p className="text-sm font-medium text-slate-800">{product.name}</p>
                </div>
                <div className="flex items-center gap-3 text-right">
                  <span className="text-xs font-semibold text-amber-700">{product.quantity} left</span>
                  <span className="text-xs text-slate-400">Min: {product.min_stock}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {ADMIN_ROLES.includes(user?.role) && (
        <StockHistoryModal product={stockHistoryProduct} open={!!stockHistoryProduct} onOpenChange={(open) => !open && setStockHistoryProduct(null)} />
      )}
    </div>
  );
};

function StatCard({ label, value, sub, accent = "slate" }) {
  const barColor = {
    emerald: "bg-emerald-400", blue: "bg-blue-400", amber: "bg-amber-400",
    orange: "bg-orange-400", slate: "bg-slate-200",
  }[accent] || "bg-slate-200";

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${barColor}`} />
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-3">{label}</p>
      <p className="text-2xl font-bold text-slate-900 tabular-nums leading-none">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-2">{sub}</p>}
    </div>
  );
}

export default Dashboard;
