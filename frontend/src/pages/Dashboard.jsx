import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  DollarSign,
  ShoppingCart,
  Package,
  AlertTriangle,
  ArrowRight,
  BarChart3,
} from "lucide-react";
import { Card, Metric, SparkAreaChart, AreaChart, Tracker } from "@tremor/react";
import { format } from "date-fns";
import { API } from "@/lib/api";
import { valueFormatter } from "@/lib/chartConfig";
import { ROLES, ADMIN_ROLES } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { RecentTransactions } from "@/components/RecentTransactions";

const Dashboard = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  const isContractor = user?.role === ROLES.CONTRACTOR;
  const isAdmin = user?.role === ROLES.ADMIN;
  const showTransactionsTerminal = ADMIN_ROLES.includes(user?.role);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);

  useEffect(() => {
    fetchStats();
    if (!isContractor) {
      seedDepartments();
    }
  }, []);

  const seedDepartments = async () => {
    try {
      await axios.post(`${API}/seed/departments`);
    } catch (error) {
      // Ignore - may already be seeded
    }
  };

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API}/dashboard/stats`);
      setStats(response.data);
    } catch (error) {
      console.error("Error fetching stats:", error);
      toast.error("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <PageSkeleton />;
  }

  // Contractor Dashboard
  if (isContractor) {
    return (
      <div className="p-8" data-testid="dashboard-page">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
            Dashboard
          </h1>
          <p className="text-slate-500 mt-1 text-sm">
            Welcome back, {user?.name} · {user?.company || "Independent"}
          </p>
        </div>

        {/* Contractor Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="card-workshop">
            <Metric>{stats?.total_withdrawals || 0}</Metric>
            <p className="text-sm text-slate-500 font-medium mt-1">Total Withdrawals</p>
          </Card>
          <Card className="card-workshop">
            <Metric color="emerald">{valueFormatter(stats?.total_spent || 0)}</Metric>
            <p className="text-sm text-slate-500 font-medium mt-1">Total Value</p>
          </Card>
          <Card className="card-workshop">
            <Metric color="amber">{valueFormatter(stats?.unpaid_balance || 0)}</Metric>
            <p className="text-sm text-slate-500 font-medium mt-1">Unpaid Balance</p>
          </Card>
        </div>

        {/* Recent Withdrawals */}
        <Card className="card-elevated p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            Recent Withdrawals
          </h2>
          {stats?.recent_withdrawals?.length > 0 ? (
            <div className="space-y-3">
              {stats.recent_withdrawals.map((w, index) => (
                <div
                  key={w.id || index}
                  className="flex items-center justify-between p-4 bg-slate-50/80 rounded-xl border border-slate-100"
                >
                  <div>
                    <p className="font-mono text-xs text-slate-500">
                      Job: {w.job_id}
                    </p>
                    <p className="text-sm text-slate-600 mt-0.5">
                      {w.items?.length || 0} items ·{" "}
                      {w.service_address?.slice(0, 30)}...
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-slate-900">
                      ${w.total?.toFixed(2)}
                    </p>
                    <span
                      className={
                        w.payment_status === "paid"
                          ? "badge-success"
                          : "badge-warning"
                      }
                    >
                      {w.payment_status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              <ShoppingCart className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="font-medium">No withdrawals yet</p>
            </div>
          )}
        </Card>
      </div>
    );
  }

  // Warehouse Manager / Admin Dashboard
  const revenueChartData = stats?.revenue_by_day?.length
    ? stats.revenue_by_day.map((d) => ({
        date: format(new Date(d.date), "MMM d"),
        Revenue: d.revenue,
      }))
    : [];

  const displayCards = [
    {
      label: "Today's Activity",
      value: valueFormatter(stats?.today_revenue || 0),
      subtext: `${stats?.today_transactions || 0} withdrawals`,
      color: "emerald",
      hasSpark: true,
    },
    {
      label: "This Week",
      value: valueFormatter(stats?.week_revenue || 0),
      subtext: "Last 7 days",
      color: "blue",
      hasSpark: true,
    },
    {
      label: "Total Products",
      value: stats?.total_products || 0,
      color: "slate",
      adminOnly: false,
    },
    {
      label: "Low Stock Items",
      value: stats?.low_stock_count || 0,
      color: "amber",
      adminOnly: false,
    },
    {
      label: "Contractors",
      value: stats?.total_contractors || 0,
      color: "violet",
      adminOnly: true,
    },
    {
      label: "Total Vendors",
      value: stats?.total_vendors || 0,
      color: "slate",
      adminOnly: false,
    },
  ].filter((card) => !card.adminOnly || isAdmin);

  const trackerData =
    stats?.recent_withdrawals?.map((w, i) => ({
      key: w.id || i,
      color: w.payment_status === "paid" ? "emerald" : "amber",
      tooltip: `${w.contractor_name || "Unknown"} · ${valueFormatter(w.total)} · ${w.payment_status}`,
    })) || [];

  return (
    <div className="p-8" data-testid="dashboard-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Dashboard
        </h1>
        <p className="text-slate-500 mt-1 text-sm">
          Welcome back, {user?.name}
        </p>
      </div>

      {(stats?.low_stock_count > 0 || (isAdmin && stats?.unpaid_total > 0)) && (
        <div className="mb-6">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Needs Attention
          </p>
          <div className="flex flex-wrap gap-2">
            {stats?.low_stock_count > 0 && (
              <Link
                to="/inventory?low_stock=1"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 hover:border-amber-400 transition-colors group"
              >
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span className="text-sm font-semibold text-amber-800">
                  {stats.low_stock_count} items low on stock
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-amber-400 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            )}
            {isAdmin && stats?.unpaid_total > 0 && (
              <Link
                to="/financials"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-rose-50 border border-rose-200 hover:border-rose-400 transition-colors group"
              >
                <DollarSign className="w-4 h-4 text-rose-500" />
                <span className="text-sm font-semibold text-rose-800">
                  ${(stats.unpaid_total).toLocaleString("en-US", { minimumFractionDigits: 2 })} unpaid balance
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-rose-400 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            )}
          </div>
        </div>
      )}

      <div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6 mb-8"
        data-testid="stats-grid"
      >
        {displayCards.map((stat, index) => (
          <Card
            key={index}
            className="card-workshop animate-slide-in"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            {stat.hasSpark && revenueChartData.length > 0 ? (
              <>
                <Metric color={stat.color}>{stat.value}</Metric>
                <p className="text-sm text-slate-500 font-medium mt-1">{stat.label}</p>
                {stat.subtext && <p className="text-xs text-slate-400 mt-2">{stat.subtext}</p>}
                <SparkAreaChart
                  data={revenueChartData}
                  index="date"
                  categories={["Revenue"]}
                  colors={[stat.color]}
                  className="mt-4 h-12"
                />
              </>
            ) : (
              <>
                <Metric color={stat.color}>{stat.value}</Metric>
                <p className="text-sm text-slate-500 font-medium mt-1">{stat.label}</p>
                {stat.subtext && <p className="text-xs text-slate-400 mt-2">{stat.subtext}</p>}
              </>
            )}
          </Card>
        ))}
      </div>

      {/* Revenue chart */}
      {revenueChartData.length > 0 && (
        <Card className="card-workshop p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-900">Revenue — Last 7 Days</h2>
            <Link to="/reports" className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1">
              View reports <BarChart3 className="w-4 h-4" />
            </Link>
          </div>
          <AreaChart
            data={revenueChartData}
            index="date"
            categories={["Revenue"]}
            colors={["orange"]}
            valueFormatter={valueFormatter}
            showLegend={false}
            className="h-48"
          />
        </Card>
      )}

      {showTransactionsTerminal && (
        <RecentTransactions onProductStockHistory={setStockHistoryProduct} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="card-workshop p-6" data-testid="recent-sales-card">
          <div className="flex items-center justify-between mb-5 pb-4 border-b border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">Recent Withdrawals</h2>
            <Link to="/financials" className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1">
              View all <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          {trackerData.length > 0 ? (
            <div className="space-y-4">
              <Tracker data={trackerData} className="mt-2" />
              <div className="text-xs text-slate-500 mt-3">
                Hover over blocks for details · Green = paid, Amber = unpaid
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              <ShoppingCart className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="font-medium">No withdrawals yet</p>
            </div>
          )}
        </Card>

        <Card className="card-workshop p-6" data-testid="low-stock-card">
          <div className="flex items-center justify-between mb-5 pb-4 border-b border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">Low Stock Alerts</h2>
            <Link to="/inventory?low_stock=1" className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1">
              View in Inventory <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          {stats?.low_stock_alerts?.length > 0 ? (
            <div className="space-y-3">
              {stats.low_stock_alerts.map((product, index) => (
                <Link key={product.id || index} to="/inventory" className="block">
                  <div className="flex items-center justify-between p-4 bg-amber-50/80 rounded-xl border border-amber-200/80 hover:border-amber-300 transition-colors">
                    <div>
                      <p className="font-mono text-xs text-amber-700">{product.sku}</p>
                      <p className="font-medium text-slate-800">{product.name}</p>
                    </div>
                    <div className="text-right flex items-center gap-2">
                      <span className="badge-warning">{product.quantity} left</span>
                      <p className="text-xs text-slate-500">Min: {product.min_stock}</p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-400">
              <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="font-medium">All products well stocked</p>
            </div>
          )}
        </Card>
      </div>

      {ADMIN_ROLES.includes(user?.role) && (
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
