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
  Users,
  TrendingUp,
  HardHat,
  Clock,
  ArrowRight,
  BarChart3,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { format } from "date-fns";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Dashboard = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  const isContractor = user?.role === "contractor";
  const isAdmin = user?.role === "admin";

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
    return (
      <div className="p-8 flex items-center justify-center min-h-[50vh]">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <span className="font-medium">Loading dashboard…</span>
        </div>
      </div>
    );
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
          <div className="card-workshop p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-11 h-11 bg-blue-50 rounded-xl flex items-center justify-center">
                <ShoppingCart className="w-5 h-5 text-blue-600" />
              </div>
            </div>
            <p className="text-sm text-slate-500 font-medium">
              Total Withdrawals
            </p>
            <p className="text-2xl font-semibold text-slate-900 mt-1 tracking-tight">
              {stats?.total_withdrawals || 0}
            </p>
          </div>

          <div className="card-workshop p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-11 h-11 bg-emerald-50 rounded-xl flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-emerald-600" />
              </div>
            </div>
            <p className="text-sm text-slate-500 font-medium">Total Value</p>
            <p className="text-2xl font-semibold text-emerald-600 mt-1 tracking-tight">
              $
              {(stats?.total_spent || 0).toLocaleString("en-US", {
                minimumFractionDigits: 2,
              })}
            </p>
          </div>

          <div className="card-workshop p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-11 h-11 bg-amber-50 rounded-xl flex items-center justify-center">
                <Clock className="w-5 h-5 text-amber-600" />
              </div>
            </div>
            <p className="text-sm text-slate-500 font-medium">Unpaid Balance</p>
            <p className="text-2xl font-semibold text-amber-600 mt-1 tracking-tight">
              $
              {(stats?.unpaid_balance || 0).toLocaleString("en-US", {
                minimumFractionDigits: 2,
              })}
            </p>
          </div>
        </div>

        {/* Recent Withdrawals */}
        <div className="card-elevated p-6">
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
        </div>
      </div>
    );
  }

  // Warehouse Manager / Admin Dashboard
  const statCards = [
    {
      label: "Today's Activity",
      value: `$${(stats?.today_revenue || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
      subtext: `${stats?.today_transactions || 0} withdrawals`,
      icon: DollarSign,
      color: "text-emerald-600",
      bgColor: "bg-emerald-50",
    },
    {
      label: "This Week",
      value: `$${(stats?.week_revenue || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
      subtext: "Last 7 days",
      icon: TrendingUp,
      color: "text-blue-600",
      bgColor: "bg-blue-50",
    },
    {
      label: "Total Products",
      value: stats?.total_products || 0,
      icon: Package,
      color: "text-slate-600",
      bgColor: "bg-slate-100",
    },
    {
      label: "Low Stock Items",
      value: stats?.low_stock_count || 0,
      icon: AlertTriangle,
      color: "text-amber-600",
      bgColor: "bg-amber-50",
    },
    {
      label: "Contractors",
      value: stats?.total_contractors || 0,
      icon: HardHat,
      color: "text-violet-600",
      bgColor: "bg-violet-50",
      adminOnly: true,
    },
    {
      label: "Total Vendors",
      value: stats?.total_vendors || 0,
      icon: Users,
      color: "text-slate-600",
      bgColor: "bg-slate-100",
    },
  ];

  const displayCards = statCards.filter(
    (card) => !card.adminOnly || isAdmin
  );

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

      {isAdmin && stats?.unpaid_total > 0 && (
        <Link to="/financials">
          <div className="card-workshop p-5 mb-6 border-rose-200 bg-rose-50/50 hover:border-rose-300 cursor-pointer transition-colors">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-rose-100 rounded-xl flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-rose-600" />
                </div>
                <div>
                  <p className="font-semibold text-rose-800">Outstanding Balance</p>
                  <p className="text-sm text-rose-600">Unpaid contractor withdrawals — View all</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <p className="text-xl font-semibold text-rose-600">
                  ${(stats?.unpaid_total || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </p>
                <ArrowRight className="w-5 h-5 text-rose-500" />
              </div>
            </div>
          </div>
        </Link>
      )}

      <div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6 mb-8"
        data-testid="stats-grid"
      >
        {displayCards.map((stat, index) => (
          <div
            key={index}
            className="card-workshop p-6 animate-slide-in"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex items-center justify-between mb-4">
              <div
                className={`w-11 h-11 ${stat.bgColor} rounded-xl flex items-center justify-center`}
              >
                <stat.icon className={`w-5 h-5 ${stat.color}`} />
              </div>
            </div>
            <p className="text-sm text-slate-500 font-medium">{stat.label}</p>
            <p className="text-2xl font-semibold text-slate-900 mt-1 tracking-tight">
              {stat.value}
            </p>
            {stat.subtext && (
              <p className="text-xs text-slate-400 mt-2">{stat.subtext}</p>
            )}
          </div>
        ))}
      </div>

      {/* Revenue chart */}
      {stats?.revenue_by_day?.length > 0 && (
        <div className="card-workshop p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-900">Revenue — Last 7 Days</h2>
            <Link to="/reports" className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1">
              View reports <BarChart3 className="w-4 h-4" />
            </Link>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.revenue_by_day.map((d) => ({ ...d, day: format(new Date(d.date), "EEE") }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
                <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, "Revenue"]} />
                <Bar dataKey="revenue" fill="#f97316" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-workshop p-6" data-testid="recent-sales-card">
          <div className="flex items-center justify-between mb-5 pb-4 border-b border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">Recent Withdrawals</h2>
            <Link to="/financials" className="text-sm text-slate-500 hover:text-orange-600 flex items-center gap-1">
              View all <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          {stats?.recent_withdrawals?.length > 0 ? (
            <div className="space-y-3">
              {stats.recent_withdrawals.map((w, index) => (
                <div
                  key={w.id || index}
                  className="flex items-center justify-between p-4 bg-slate-50/80 rounded-xl border border-slate-100"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <HardHat className="w-4 h-4 text-slate-400" />
                      <span className="font-medium text-slate-800">
                        {w.contractor_name || "Unknown"}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5">
                      {w.items?.length || 0} items · Job: {w.job_id}
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
        </div>

        <div className="card-workshop p-6" data-testid="low-stock-card">
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
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
