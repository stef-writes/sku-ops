import { useState, useEffect, useMemo } from "react";
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
  Download,
  ShoppingCart,
  ArrowRight,
  Layers,
  Briefcase,
} from "lucide-react";
import { format } from "date-fns";
import { AreaChart } from "@tremor/react";

import { API } from "@/lib/api";
import { valueFormatter } from "@/lib/chartConfig";
import { DATE_PRESETS } from "@/lib/constants";

// ─── Stat card ───────────────────────────────────────────────────────────────
const Stat = ({ label, value, icon: Icon, accent = "amber", note, large }) => {
  const cfg = {
    amber:   { bar: "bg-amber-400",   icon: "bg-amber-50 text-amber-600" },
    emerald: { bar: "bg-emerald-400", icon: "bg-emerald-50 text-emerald-600" },
    blue:    { bar: "bg-blue-400",    icon: "bg-blue-50 text-blue-600" },
    orange:  { bar: "bg-orange-400",  icon: "bg-orange-50 text-orange-600" },
    violet:  { bar: "bg-violet-400",  icon: "bg-violet-50 text-violet-600" },
    slate:   { bar: "bg-slate-300",   icon: "bg-slate-50 text-slate-500" },
  }[accent] || { bar: "bg-amber-400", icon: "bg-amber-50 text-amber-600" };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 relative overflow-hidden shadow-sm">
      <div className={`absolute top-0 left-0 right-0 h-[3px] ${cfg.bar}`} />
      <div className="flex items-start justify-between mb-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${cfg.icon}`}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
      <p className={`font-bold text-slate-900 tabular-nums leading-none ${large ? "text-4xl" : "text-2xl"}`}>{value}</p>
      {note && <p className="text-xs text-slate-400 mt-2">{note}</p>}
    </div>
  );
};

// ─── Custom horizontal product bar ───────────────────────────────────────────
const ProductBars = ({ products }) => {
  const max = useMemo(() => Math.max(...products.map((p) => p.revenue), 1), [products]);
  return (
    <div className="space-y-0 divide-y divide-slate-50">
      {products.map((p, i) => (
        <div key={i} className="flex items-center gap-3 py-2.5">
          <span className="text-[10px] font-bold text-slate-300 w-4 shrink-0 tabular-nums">{i + 1}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-700 truncate mb-1.5">{p.name}</p>
            <div className="h-[5px] bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-400 rounded-full transition-all duration-700"
                style={{ width: `${((p.revenue / max) * 100).toFixed(1)}%` }}
              />
            </div>
          </div>
          <div className="text-right shrink-0">
            <p className="text-sm font-bold text-slate-900 tabular-nums">{valueFormatter(p.revenue)}</p>
            <p className="text-[10px] text-slate-400 tabular-nums">{p.quantity} units</p>
          </div>
        </div>
      ))}
    </div>
  );
};

// ─── Payment status proportion strip ─────────────────────────────────────────
const PaymentStrip = ({ data }) => {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const palette = { Paid: "#34d399", Invoiced: "#60a5fa", Unpaid: "#fb923c", Unknown: "#94a3b8" };
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden gap-px mb-3">
        {data.map((d) => (
          <div
            key={d.name}
            style={{ width: `${(d.value / total) * 100}%`, backgroundColor: palette[d.name] || "#94a3b8" }}
            title={`${d.name}: ${valueFormatter(d.value)}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: palette[d.name] || "#94a3b8" }} />
            <span className="text-xs text-slate-500">{d.name}</span>
            <span className="text-xs font-bold text-slate-700 tabular-nums">{valueFormatter(d.value)}</span>
            <span className="text-[10px] text-slate-400">({((d.value / total) * 100).toFixed(0)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Department stacked bars ──────────────────────────────────────────────────
const DeptBars = ({ data }) => {
  const max = useMemo(() => Math.max(...data.map((d) => d.value), 1), [data]);
  const sorted = [...data].sort((a, b) => b.value - a.value);
  return (
    <div className="space-y-3">
      {sorted.map((d) => (
        <div key={d.name}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-slate-700">{d.name}</span>
            <div className="flex items-center gap-3 text-xs tabular-nums">
              <span className="text-slate-500">{valueFormatter(d.cost)} cost</span>
              <span className="font-bold text-slate-900">{valueFormatter(d.value)} retail</span>
            </div>
          </div>
          <div className="relative h-4 bg-slate-100 rounded-md overflow-hidden">
            <div
              className="absolute left-0 top-0 h-full bg-emerald-200 rounded-md transition-all duration-500"
              style={{ width: `${(d.value / max) * 100}%` }}
            />
            <div
              className="absolute left-0 top-0 h-full bg-orange-300 rounded-md transition-all duration-500"
              style={{ width: `${(d.cost / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
      <div className="flex items-center gap-4 pt-1">
        <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-orange-300" /><span className="text-xs text-slate-500">Cost value</span></div>
        <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-emerald-200" /><span className="text-xs text-slate-500">Retail value</span></div>
      </div>
    </div>
  );
};

// ─── Low stock depletion list ─────────────────────────────────────────────────
const LowStockList = ({ items }) => (
  <div className="divide-y divide-slate-50">
    {items.map((item, i) => {
      const pct = item.min_stock > 0 ? Math.min((item.quantity / item.min_stock) * 100, 100) : 0;
      const isEmpty = item.quantity === 0;
      return (
        <div key={i} className="py-3 flex items-center gap-3">
          <div className={`w-1.5 h-8 rounded-full shrink-0 ${isEmpty ? "bg-red-500" : "bg-orange-400"}`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1">
              <p className="text-sm font-medium text-slate-800 truncate">{item.name}</p>
              <span className={`text-sm font-bold tabular-nums ml-3 shrink-0 ${isEmpty ? "text-red-600" : "text-orange-600"}`}>
                {item.quantity} left
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${isEmpty ? "bg-red-400" : "bg-orange-400"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-[10px] text-slate-400 w-16 text-right shrink-0 tabular-nums">
                min {item.min_stock}
              </span>
            </div>
          </div>
        </div>
      );
    })}
  </div>
);

// ─── Margin rows with inline bar ──────────────────────────────────────────────
const MarginList = ({ margins }) => (
  <div className="divide-y divide-slate-50">
    {margins.map((p, i) => {
      const isHigh = p.margin_pct >= 40;
      const isLow = p.margin_pct < 30;
      return (
        <div key={i} className="py-3 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">{p.name}</p>
            <p className="text-[10px] text-slate-400 mt-0.5 tabular-nums">{p.quantity} units · {valueFormatter(p.cost)} COGS</p>
            <div className="mt-1.5 h-1.5 bg-slate-100 rounded-full overflow-hidden w-full">
              <div
                className={`h-full rounded-full transition-all duration-700 ${isHigh ? "bg-emerald-400" : isLow ? "bg-orange-400" : "bg-blue-400"}`}
                style={{ width: `${Math.min(p.margin_pct, 100)}%` }}
              />
            </div>
          </div>
          <div className="text-right shrink-0 ml-2">
            <p className={`text-sm font-bold tabular-nums ${isHigh ? "text-emerald-600" : isLow ? "text-orange-600" : "text-blue-600"}`}>
              {p.margin_pct}%
            </p>
            <p className="text-[10px] text-slate-400 tabular-nums">{valueFormatter(p.profit)}</p>
          </div>
        </div>
      );
    })}
  </div>
);

// ─── Section heading ──────────────────────────────────────────────────────────
const SectionHead = ({ title, action }) => (
  <div className="flex items-center justify-between mb-4">
    <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400 border-l-2 border-amber-400 pl-3">
      {title}
    </h3>
    {action}
  </div>
);

// ─── Panel wrapper ────────────────────────────────────────────────────────────
const Panel = ({ children, className = "" }) => (
  <div className={`bg-white rounded-xl border border-slate-200 shadow-sm p-6 ${className}`}>
    {children}
  </div>
);

// ═════════════════════════════════════════════════════════════════════════════
const Reports = () => {
  const [activeTab, setActiveTab] = useState("sales");
  const [salesReport, setSalesReport] = useState(null);
  const [inventoryReport, setInventoryReport] = useState(null);
  const [trendsReport, setTrendsReport] = useState(null);
  const [jobPlReport, setJobPlReport] = useState(null);
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState({ from: null, to: null });

  useEffect(() => { fetchReports(); }, [dateRange, trendsGroupBy]);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateRange.from) params.append("start_date", dateRange.from.toISOString());
      if (dateRange.to) params.append("end_date", dateRange.to.toISOString());

      const [salesRes, inventoryRes, trendsRes, marginsRes, jobPlRes] = await Promise.all([
        axios.get(`${API}/reports/sales?${params}`),
        axios.get(`${API}/reports/inventory`),
        axios.get(`${API}/reports/trends?${params}&group_by=${trendsGroupBy}`),
        axios.get(`${API}/reports/product-margins?${params}`),
        axios.get(`${API}/reports/job-pl?${params}`),
      ]);

      setSalesReport(salesRes.data);
      setInventoryReport(inventoryRes.data);
      setTrendsReport({ ...trendsRes.data, margins: marginsRes.data.products });
      setJobPlReport(jobPlRes.data);
    } catch (error) {
      console.error("Error fetching reports:", error);
      toast.error("Failed to load reports");
    } finally {
      setLoading(false);
    }
  };

  const paymentChartData = salesReport?.by_payment_status
    ? Object.entries(salesReport.by_payment_status).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: parseFloat(value.toFixed(2)),
      }))
    : [];

  const departmentChartData = inventoryReport?.by_department
    ? Object.entries(inventoryReport.by_department).map(([name, data]) => ({
        name,
        count: data.count,
        value: parseFloat(data.value.toFixed(2)),
        cost: parseFloat((data.cost || 0).toFixed(2)),
      }))
    : [];

  const handleExportCSV = () => {
    const rows = [];
    if (activeTab === "sales" && salesReport) {
      rows.push(["Report", "Sales Report"]);
      rows.push(["Date Range", dateRange.from ? (dateRange.to ? `${format(dateRange.from, "yyyy-MM-dd")} to ${format(dateRange.to, "yyyy-MM-dd")}` : format(dateRange.from, "yyyy-MM-dd")) : "All time"]);
      rows.push([]);
      rows.push(["Metric", "Value"]);
      rows.push(["Total Revenue", salesReport.total_revenue]);
      rows.push(["Total Transactions", salesReport.total_transactions]);
      rows.push(["Average Transaction", salesReport.average_transaction]);
      rows.push(["Total Tax", salesReport.total_tax]);
      if (salesReport.top_products?.length) {
        rows.push([]);
        rows.push(["Top Products", "Name", "Revenue", "Quantity"]);
        salesReport.top_products.forEach((p) => rows.push([p.name, p.revenue, p.quantity]));
      }
    } else if (activeTab === "inventory" && inventoryReport) {
      rows.push(["Report", "Inventory Report"]);
      rows.push([]);
      rows.push(["Metric", "Value"]);
      rows.push(["Total Products", inventoryReport.total_products]);
      rows.push(["Retail Value", inventoryReport.total_retail_value]);
      rows.push(["Cost Value", inventoryReport.total_cost_value]);
      rows.push(["Potential Profit", inventoryReport.potential_profit]);
      rows.push(["Low Stock Count", inventoryReport.low_stock_count]);
      rows.push(["Out of Stock Count", inventoryReport.out_of_stock_count]);
    } else if (activeTab === "trends" && trendsReport) {
      rows.push(["Report", "Trends Report"]);
      rows.push(["Group By", trendsGroupBy]);
      rows.push(["Date Range", dateRange.from ? (dateRange.to ? `${format(dateRange.from, "yyyy-MM-dd")} to ${format(dateRange.to, "yyyy-MM-dd")}` : format(dateRange.from, "yyyy-MM-dd")) : "All time"]);
      rows.push([]);
      rows.push(["Period", "Revenue", "Cost", "Profit"]);
      trendsReport.series.forEach((r) => rows.push([r.date, r.revenue, r.cost, r.profit]));
      if (trendsReport.margins?.length) {
        rows.push([]);
        rows.push(["Product Margins", "Name", "Revenue", "Cost", "Profit", "Margin %", "Units Sold"]);
        trendsReport.margins.forEach((p) => rows.push([p.name, p.revenue, p.cost, p.profit, p.margin_pct, p.quantity]));
      }
    } else if (activeTab === "job-pl" && jobPlReport) {
      rows.push(["Report", "Job P&L"]);
      rows.push(["Date Range", dateRange.from ? (dateRange.to ? `${format(dateRange.from, "yyyy-MM-dd")} to ${format(dateRange.to, "yyyy-MM-dd")}` : format(dateRange.from, "yyyy-MM-dd")) : "All time"]);
      rows.push([]);
      rows.push(["Total Revenue", jobPlReport.total_revenue]);
      rows.push(["Total COGS", jobPlReport.total_cost]);
      rows.push(["Total Profit", jobPlReport.total_profit]);
      rows.push(["Overall Margin %", jobPlReport.total_margin_pct]);
      rows.push([]);
      rows.push(["Job ID", "Customer", "Withdrawals", "Revenue", "COGS", "Profit", "Margin %"]);
      jobPlReport.jobs.forEach((j) => rows.push([j.job_id, j.billing_entity, j.withdrawal_count, j.revenue, j.cost, j.profit, j.margin_pct]));
    }
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report-${activeTab}-${format(new Date(), "yyyy-MM-dd")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ─── Inventory health breakdown ─────────────────────────────────────────────
  const inStock = (inventoryReport?.total_products || 0)
    - (inventoryReport?.low_stock_count || 0)
    - (inventoryReport?.out_of_stock_count || 0);
  const totalP = inventoryReport?.total_products || 1;

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-500 font-medium">Loading reports…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="reports-page">
      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">Reports</h1>
          <p className="text-slate-500 mt-1 text-sm">Sales, inventory, and profit analytics</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
            {DATE_PRESETS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => setDateRange(preset.getValue())}
                className="text-xs px-3 py-1.5 rounded-md text-slate-600 hover:bg-white hover:shadow-sm transition-all font-medium"
              >
                {preset.label}
              </button>
            ))}
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="h-9 px-3 text-sm gap-2" data-testid="date-range-btn">
                <CalendarIcon className="w-4 h-4" />
                {dateRange.from
                  ? dateRange.to
                    ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}`
                    : format(dateRange.from, "MMM d, yyyy")
                  : "Custom range"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar mode="range" selected={dateRange} onSelect={(r) => setDateRange(r || { from: null, to: null })} numberOfMonths={2} />
            </PopoverContent>
          </Popover>
          {(dateRange.from || dateRange.to) && (
            <button onClick={() => setDateRange({ from: null, to: null })} className="text-xs text-slate-400 hover:text-slate-600" data-testid="clear-date-btn">
              Clear
            </button>
          )}
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-2" data-testid="export-csv-btn">
            <Download className="w-4 h-4" />
            Export
          </Button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-transparent border-b border-slate-200 rounded-none p-0 h-auto gap-0 w-full justify-start" data-testid="report-tabs">
          {[
            { value: "sales", label: "Sales", icon: BarChart3 },
            { value: "inventory", label: "Inventory", icon: Package },
            { value: "trends", label: "Trends & Margins", icon: TrendingUp },
            { value: "job-pl", label: "Job P&L", icon: Briefcase },
          ].map(({ value, label, icon: Icon }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-slate-900 text-slate-500 px-5 py-3 text-sm font-semibold gap-2 bg-transparent shadow-none"
              data-testid={`${value}-tab`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* ══ SALES ══════════════════════════════════════════════════════════ */}
        <TabsContent value="sales" className="space-y-6 mt-6" data-testid="sales-report-content">
          {/* Hero metric + supporting stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="md:col-span-1 bg-gradient-to-br from-amber-500 to-orange-500 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(salesReport?.total_revenue || 0)}</p>
              <p className="text-xs text-amber-200 mt-3">
                {salesReport?.total_transactions || 0} transactions
              </p>
            </div>
            <Stat label="COGS" value={valueFormatter(salesReport?.total_cogs || 0)} icon={DollarSign} accent="orange" note="cost of goods sold" />
            <Stat label="Gross Profit" value={valueFormatter(salesReport?.gross_profit || 0)} icon={TrendingUp} accent="emerald" note={`${salesReport?.gross_margin_pct ?? 0}% margin`} />
            <Stat label="Avg Transaction" value={valueFormatter(salesReport?.average_transaction || 0)} icon={ArrowRight} accent="violet" note="per order" />
          </div>

          {/* Payment breakdown */}
          <Panel>
            <SectionHead title="Sales by Payment Status" />
            {paymentChartData.length > 0 ? (
              <PaymentStrip data={paymentChartData} />
            ) : (
              <p className="text-sm text-slate-400 py-8 text-center">No sales data available</p>
            )}
          </Panel>

          {/* Top products */}
          <Panel>
            <SectionHead title="Top Selling Products" />
            {salesReport?.top_products?.length > 0 ? (
              <ProductBars products={salesReport.top_products.slice(0, 10)} />
            ) : (
              <div className="py-12 text-center">
                <Package className="w-10 h-10 mx-auto text-slate-200 mb-3" />
                <p className="text-sm text-slate-400">No sales data available</p>
              </div>
            )}
          </Panel>
        </TabsContent>

        {/* ══ INVENTORY ══════════════════════════════════════════════════════ */}
        <TabsContent value="inventory" className="space-y-6 mt-6" data-testid="inventory-report-content">
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Total Products" value={inventoryReport?.total_products || 0} icon={Package} accent="blue" />
            <Stat label="Retail Value" value={valueFormatter(inventoryReport?.total_retail_value || 0)} icon={DollarSign} accent="emerald" />
            <Stat label="Cost Value" value={valueFormatter(inventoryReport?.total_cost_value || 0)} icon={Layers} accent="slate" />
            <Stat label="Potential Profit" value={valueFormatter(inventoryReport?.potential_profit || 0)} icon={TrendingUp} accent="amber" />
          </div>

          {/* Stock health bar */}
          <Panel>
            <SectionHead title="Stock Health" />
            <div className="flex h-5 rounded-lg overflow-hidden gap-px mb-3">
              <div className="bg-emerald-400 transition-all duration-700" style={{ width: `${(inStock / totalP) * 100}%` }} />
              <div className="bg-orange-400 transition-all duration-700" style={{ width: `${((inventoryReport?.low_stock_count || 0) / totalP) * 100}%` }} />
              <div className="bg-red-500 transition-all duration-700" style={{ width: `${((inventoryReport?.out_of_stock_count || 0) / totalP) * 100}%` }} />
            </div>
            <div className="flex gap-5 text-xs">
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />In stock <strong className="tabular-nums">{inStock}</strong></span>
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-orange-400 inline-block" />Low stock <strong className="tabular-nums">{inventoryReport?.low_stock_count || 0}</strong></span>
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" />Out of stock <strong className="tabular-nums">{inventoryReport?.out_of_stock_count || 0}</strong></span>
            </div>
          </Panel>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Department breakdown */}
            <Panel>
              <SectionHead title="Value by Department" />
              {departmentChartData.length > 0 ? (
                <DeptBars data={departmentChartData} />
              ) : (
                <p className="text-sm text-slate-400 py-8 text-center">No inventory data</p>
              )}
            </Panel>

            {/* Low stock */}
            <Panel>
              <SectionHead
                title="Low Stock Alert"
                action={
                  inventoryReport?.low_stock_items?.length > 0 && (
                    <span className="text-xs font-bold text-orange-500 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200">
                      {inventoryReport.low_stock_count} items
                    </span>
                  )
                }
              />
              {inventoryReport?.low_stock_items?.length > 0 ? (
                <div className="max-h-[360px] overflow-auto -mx-6 px-6">
                  <LowStockList items={inventoryReport.low_stock_items} />
                </div>
              ) : (
                <div className="py-12 text-center">
                  <Package className="w-10 h-10 mx-auto text-slate-200 mb-3" />
                  <p className="text-sm text-slate-500 font-medium">All products well stocked</p>
                </div>
              )}
            </Panel>
          </div>
        </TabsContent>

        {/* ══ TRENDS ═════════════════════════════════════════════════════════ */}
        <TabsContent value="trends" className="space-y-6 mt-6" data-testid="trends-report-content">
          {/* Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-100 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(trendsReport?.totals?.revenue || 0)}</p>
            </div>
            <Stat label="Total Cost (COGS)" value={valueFormatter(trendsReport?.totals?.cost || 0)} icon={DollarSign} accent="orange" />
            <Stat label="Gross Profit" value={valueFormatter(trendsReport?.totals?.profit || 0)} icon={TrendingUp} accent="blue" />
          </div>

          {/* Area chart */}
          <Panel>
            <SectionHead
              title="Revenue, Cost & Profit Over Time"
              action={
                <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
                  {["day", "week", "month"].map((g) => (
                    <button
                      key={g}
                      onClick={() => setTrendsGroupBy(g)}
                      className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${
                        trendsGroupBy === g
                          ? "bg-white shadow-sm text-slate-900"
                          : "text-slate-500 hover:text-slate-700"
                      }`}
                    >
                      {g.charAt(0).toUpperCase() + g.slice(1)}
                    </button>
                  ))}
                </div>
              }
            />
            {trendsReport?.series?.length > 0 ? (
              <AreaChart
                data={trendsReport.series}
                index="date"
                categories={["revenue", "cost", "profit"]}
                colors={["emerald", "orange", "blue"]}
                valueFormatter={valueFormatter}
                className="h-[280px] mt-2"
              />
            ) : (
              <div className="h-[280px] flex items-center justify-center">
                <p className="text-sm text-slate-400">No trend data for this period</p>
              </div>
            )}
          </Panel>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top by revenue */}
            <Panel>
              <SectionHead title="Top Products by Revenue" />
              {trendsReport?.margins?.length > 0 ? (
                <ProductBars products={trendsReport.margins.slice(0, 10).map((p) => ({ name: p.name, revenue: p.revenue, quantity: p.quantity }))} />
              ) : (
                <p className="text-sm text-slate-400 py-8 text-center">No data available</p>
              )}
            </Panel>

            {/* Margin list */}
            <Panel>
              <SectionHead title="Profit Margin by Product" />
              <div className="flex items-center gap-4 mb-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-400 inline-block" />≥40% high</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-400 inline-block" />30–40%</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-400 inline-block" />&lt;30% low</span>
              </div>
              {trendsReport?.margins?.length > 0 ? (
                <div className="max-h-[360px] overflow-auto -mx-6 px-6">
                  <MarginList margins={trendsReport.margins} />
                </div>
              ) : (
                <p className="text-sm text-slate-400 py-8 text-center">No margin data available</p>
              )}
            </Panel>
          </div>
        </TabsContent>

        {/* ══ JOB P&L ════════════════════════════════════════════════════════ */}
        <TabsContent value="job-pl" className="space-y-6 mt-6" data-testid="job-pl-report-content">
          {/* Summary stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-violet-100 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(jobPlReport?.total_revenue || 0)}</p>
              <p className="text-xs text-violet-200 mt-3">{jobPlReport?.jobs?.length || 0} jobs</p>
            </div>
            <Stat label="Total COGS" value={valueFormatter(jobPlReport?.total_cost || 0)} icon={DollarSign} accent="orange" note="cost of goods sold" />
            <Stat label="Gross Profit" value={valueFormatter(jobPlReport?.total_profit || 0)} icon={TrendingUp} accent="emerald" note={`${jobPlReport?.total_margin_pct ?? 0}% overall margin`} />
            <Stat label="Jobs Tracked" value={jobPlReport?.jobs?.length || 0} icon={Briefcase} accent="blue" note="unique job IDs" />
          </div>

          {/* Job table */}
          <Panel>
            <SectionHead title="P&L by Job" />
            {jobPlReport?.jobs?.length > 0 ? (
              <div className="overflow-x-auto -mx-6 px-6">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100">
                      {["Job ID", "Customer", "Orders", "Revenue", "COGS", "Profit", "Margin"].map((h) => (
                        <th key={h} className="text-left text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 pb-3 pr-4 last:pr-0">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {jobPlReport.jobs.map((job, i) => {
                      const isHigh = job.margin_pct >= 40;
                      const isLow = job.margin_pct < 30;
                      return (
                        <tr key={i} className="hover:bg-slate-50 transition-colors">
                          <td className="py-3 pr-4 font-mono text-xs font-bold text-slate-700">{job.job_id}</td>
                          <td className="py-3 pr-4 text-slate-600 max-w-[160px] truncate">{job.billing_entity || "—"}</td>
                          <td className="py-3 pr-4 tabular-nums text-slate-500">{job.withdrawal_count}</td>
                          <td className="py-3 pr-4 tabular-nums font-semibold text-slate-900">{valueFormatter(job.revenue)}</td>
                          <td className="py-3 pr-4 tabular-nums text-slate-500">{valueFormatter(job.cost)}</td>
                          <td className="py-3 pr-4 tabular-nums font-semibold text-slate-900">{valueFormatter(job.profit)}</td>
                          <td className="py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold tabular-nums ${
                              isHigh ? "bg-emerald-50 text-emerald-700" : isLow ? "bg-orange-50 text-orange-700" : "bg-blue-50 text-blue-700"
                            }`}>
                              {job.margin_pct}%
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-12 text-center">
                <Briefcase className="w-10 h-10 mx-auto text-slate-200 mb-3" />
                <p className="text-sm text-slate-400">No job data for this period</p>
              </div>
            )}
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Reports;
