import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "../components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  BarChart3,
  TrendingUp,
  Package,
  DollarSign,
  Calendar as CalendarIcon,
  AlertTriangle,
  ShoppingCart,
} from "lucide-react";
import { format } from "date-fns";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const COLORS = ["#f97316", "#0f172a", "#15803d", "#3b82f6", "#8b5cf6", "#ec4899"];

const Reports = () => {
  const [activeTab, setActiveTab] = useState("sales");
  const [salesReport, setSalesReport] = useState(null);
  const [inventoryReport, setInventoryReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState({
    from: null,
    to: null,
  });

  useEffect(() => {
    fetchReports();
  }, [dateRange]);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateRange.from) {
        params.append("start_date", dateRange.from.toISOString());
      }
      if (dateRange.to) {
        params.append("end_date", dateRange.to.toISOString());
      }

      const [salesRes, inventoryRes] = await Promise.all([
        axios.get(`${API}/reports/sales?${params}`),
        axios.get(`${API}/reports/inventory`),
      ]);

      setSalesReport(salesRes.data);
      setInventoryReport(inventoryRes.data);
    } catch (error) {
      console.error("Error fetching reports:", error);
      toast.error("Failed to load reports");
    } finally {
      setLoading(false);
    }
  };

  const paymentChartData = salesReport?.by_payment_method
    ? Object.entries(salesReport.by_payment_method).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: parseFloat(value.toFixed(2)),
      }))
    : [];

  const departmentChartData = inventoryReport?.by_department
    ? Object.entries(inventoryReport.by_department).map(([name, data]) => ({
        name,
        count: data.count,
        value: parseFloat(data.value.toFixed(2)),
      }))
    : [];

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Reports...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="reports-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Reports
          </h1>
          <p className="text-slate-600 mt-1">Sales and inventory analytics</p>
        </div>

        {/* Date Range Picker */}
        <div className="flex items-center gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="btn-secondary h-12 px-4" data-testid="date-range-btn">
                <CalendarIcon className="w-5 h-5 mr-2" />
                {dateRange.from ? (
                  dateRange.to ? (
                    <>
                      {format(dateRange.from, "MMM d")} - {format(dateRange.to, "MMM d")}
                    </>
                  ) : (
                    format(dateRange.from, "MMM d, yyyy")
                  )
                ) : (
                  "All Time"
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={(range) => setDateRange(range || { from: null, to: null })}
                numberOfMonths={2}
              />
            </PopoverContent>
          </Popover>
          {(dateRange.from || dateRange.to) && (
            <Button
              variant="ghost"
              onClick={() => setDateRange({ from: null, to: null })}
              className="h-12"
              data-testid="clear-date-btn"
            >
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-slate-100 p-1 h-auto" data-testid="report-tabs">
          <TabsTrigger
            value="sales"
            className="px-6 py-3 font-heading uppercase tracking-wide data-[state=active]:bg-white data-[state=active]:shadow-hard-sm"
            data-testid="sales-tab"
          >
            <BarChart3 className="w-5 h-5 mr-2" />
            Sales Report
          </TabsTrigger>
          <TabsTrigger
            value="inventory"
            className="px-6 py-3 font-heading uppercase tracking-wide data-[state=active]:bg-white data-[state=active]:shadow-hard-sm"
            data-testid="inventory-tab"
          >
            <Package className="w-5 h-5 mr-2" />
            Inventory Report
          </TabsTrigger>
        </TabsList>

        {/* Sales Report Tab */}
        <TabsContent value="sales" className="space-y-6" data-testid="sales-report-content">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-green-100 rounded-sm flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-green-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Total Revenue</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                ${(salesReport?.total_revenue || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-blue-100 rounded-sm flex items-center justify-center">
                  <ShoppingCart className="w-5 h-5 text-blue-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Transactions</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                {salesReport?.total_transactions || 0}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-purple-100 rounded-sm flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-purple-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Avg Transaction</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                ${(salesReport?.average_transaction || 0).toFixed(2)}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-orange-100 rounded-sm flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-orange-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Total Tax</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                ${(salesReport?.total_tax || 0).toFixed(2)}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Payment Methods Chart */}
            <div className="card-workshop p-6">
              <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider mb-4">
                Sales by Payment Method
              </h3>
              {paymentChartData.length > 0 ? (
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={paymentChartData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, value }) => `${name}: $${value}`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {paymentChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => `$${value}`} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-slate-400">
                  No sales data available
                </div>
              )}
            </div>

            {/* Top Products */}
            <div className="card-workshop p-6">
              <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider mb-4">
                Top Selling Products
              </h3>
              {salesReport?.top_products?.length > 0 ? (
                <div className="space-y-3">
                  {salesReport.top_products.slice(0, 5).map((product, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-slate-50 rounded-sm border border-slate-200"
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-8 h-8 bg-orange-500 text-white rounded-sm flex items-center justify-center font-bold">
                          {index + 1}
                        </span>
                        <span className="font-medium">{product.name}</span>
                      </div>
                      <div className="text-right">
                        <p className="font-mono font-bold">${product.revenue.toFixed(2)}</p>
                        <p className="text-xs text-slate-400">{product.quantity} sold</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-slate-400">
                  No sales data available
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Inventory Report Tab */}
        <TabsContent value="inventory" className="space-y-6" data-testid="inventory-report-content">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-blue-100 rounded-sm flex items-center justify-center">
                  <Package className="w-5 h-5 text-blue-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Total Products</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                {inventoryReport?.total_products || 0}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-green-100 rounded-sm flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-green-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Retail Value</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                ${(inventoryReport?.total_retail_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-purple-100 rounded-sm flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-purple-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Potential Profit</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                ${(inventoryReport?.potential_profit || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="card-workshop p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-orange-100 rounded-sm flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-orange-600" />
                </div>
                <span className="text-sm text-slate-500 uppercase tracking-wide">Low Stock Items</span>
              </div>
              <p className="text-3xl font-heading font-bold text-slate-900">
                {inventoryReport?.low_stock_count || 0}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Inventory by Department Chart */}
            <div className="card-workshop p-6">
              <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider mb-4">
                Inventory Value by Department
              </h3>
              {departmentChartData.length > 0 ? (
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={departmentChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip formatter={(value) => `$${value}`} />
                      <Bar dataKey="value" fill="#f97316" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-slate-400">
                  No inventory data available
                </div>
              )}
            </div>

            {/* Low Stock Items */}
            <div className="card-workshop p-6">
              <h3 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider mb-4">
                Low Stock Alert
              </h3>
              {inventoryReport?.low_stock_items?.length > 0 ? (
                <div className="space-y-3 max-h-[300px] overflow-auto">
                  {inventoryReport.low_stock_items.map((item, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-orange-50 rounded-sm border border-orange-200"
                    >
                      <div>
                        <p className="font-mono text-sm text-orange-700">{item.sku}</p>
                        <p className="font-medium text-slate-800">{item.name}</p>
                      </div>
                      <div className="text-right">
                        <span className="badge-warning">{item.quantity} left</span>
                        <p className="text-xs text-slate-500 mt-1">Min: {item.min_stock}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-slate-400">
                  <div className="text-center">
                    <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>All products are well stocked</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Reports;
