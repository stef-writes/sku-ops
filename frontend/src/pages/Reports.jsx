import { useState, useMemo } from "react";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { BarChart3, TrendingUp, Package, DollarSign, Calendar as CalendarIcon, Download, Layers, Briefcase, Receipt } from "lucide-react";
import { format } from "date-fns";
import { AreaChart } from "@tremor/react";
import { valueFormatter } from "@/lib/chartConfig";
import { DATE_PRESETS } from "@/lib/constants";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatCard } from "@/components/StatCard";
import { DataTable } from "@/components/DataTable";
import { useReportSales, useReportInventory, useReportTrends, useReportMargins, useReportPL, useReportArAging } from "@/hooks/useReports";

const Stat = StatCard;

const ProductBars = ({ products = [] }) => {
  const max = useMemo(() => Math.max(...products.map((p) => p.revenue), 1), [products]);
  return (
    <div className="space-y-0 divide-y divide-slate-50">
      {products.map((p, i) => (
        <div key={i} className="flex items-center gap-3 py-2.5">
          <span className="text-[10px] font-bold text-slate-300 w-4 shrink-0 tabular-nums">{i + 1}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-700 truncate mb-1.5">{p.name}</p>
            <div className="h-[5px] bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-amber-400 rounded-full transition-all duration-700" style={{ width: `${((p.revenue / max) * 100).toFixed(1)}%` }} />
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

const PaymentStrip = ({ data = [] }) => {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const palette = { Paid: "#34d399", Invoiced: "#60a5fa", Unpaid: "#fb923c", Unknown: "#94a3b8" };
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden gap-px mb-3">
        {data.map((d) => <div key={d.name} style={{ width: `${(d.value / total) * 100}%`, backgroundColor: palette[d.name] || "#94a3b8" }} title={`${d.name}: ${valueFormatter(d.value)}`} />)}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: palette[d.name] || "#94a3b8" }} />
            <span className="text-xs text-slate-500">{d.name}</span>
            <span className="text-xs font-bold text-slate-700 tabular-nums">{valueFormatter(d.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const DeptBars = ({ data = [] }) => {
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
            <div className="absolute left-0 top-0 h-full bg-emerald-200 rounded-md transition-all duration-500" style={{ width: `${(d.value / max) * 100}%` }} />
            <div className="absolute left-0 top-0 h-full bg-orange-300 rounded-md transition-all duration-500" style={{ width: `${(d.cost / max) * 100}%` }} />
          </div>
        </div>
      ))}
      <div className="flex items-center gap-4 pt-1">
        <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-orange-300" /><span className="text-xs text-slate-500">Cost</span></div>
        <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-emerald-200" /><span className="text-xs text-slate-500">Retail</span></div>
      </div>
    </div>
  );
};

const LowStockList = ({ items = [] }) => (
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
              <span className={`text-sm font-bold tabular-nums ml-3 shrink-0 ${isEmpty ? "text-red-600" : "text-orange-600"}`}>{item.quantity} left</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className={`h-full rounded-full ${isEmpty ? "bg-red-400" : "bg-orange-400"}`} style={{ width: `${pct}%` }} /></div>
              <span className="text-[10px] text-slate-400 w-16 text-right shrink-0 tabular-nums">min {item.min_stock}</span>
            </div>
          </div>
        </div>
      );
    })}
  </div>
);

const MarginList = ({ margins }) => (
  <div className="divide-y divide-slate-50">
    {margins.map((p, i) => {
      const isHigh = p.margin_pct >= 40; const isLow = p.margin_pct < 30;
      return (
        <div key={i} className="py-3 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">{p.name}</p>
            <p className="text-[10px] text-slate-400 mt-0.5 tabular-nums">{p.quantity} units · {valueFormatter(p.cost)} COGS</p>
            <div className="mt-1.5 h-1.5 bg-slate-100 rounded-full overflow-hidden w-full">
              <div className={`h-full rounded-full ${isHigh ? "bg-emerald-400" : isLow ? "bg-orange-400" : "bg-blue-400"}`} style={{ width: `${Math.min(p.margin_pct, 100)}%` }} />
            </div>
          </div>
          <div className="text-right shrink-0 ml-2">
            <p className={`text-sm font-bold tabular-nums ${isHigh ? "text-emerald-600" : isLow ? "text-orange-600" : "text-blue-600"}`}>{p.margin_pct}%</p>
            <p className="text-[10px] text-slate-400 tabular-nums">{valueFormatter(p.profit)}</p>
          </div>
        </div>
      );
    })}
  </div>
);

import { Panel, SectionHead as SectionHeadBase } from "@/components/Panel";
const SectionHead = ({ title, action }) => <SectionHeadBase title={title} action={action} variant="report" />;

const PL_DIMENSIONS = [
  { value: "overall", label: "Overall" },
  { value: "job", label: "By Job" },
  { value: "department", label: "By Department" },
  { value: "entity", label: "By Entity" },
  { value: "product", label: "By Product" },
];

const PL_COLUMNS = {
  job: { label: "Job ID", key: "job_id", secondary: "billing_entity" },
  department: { label: "Department", key: "department" },
  entity: { label: "Billing Entity", key: "billing_entity" },
  product: { label: "Product", key: "product_id" },
};

const PLBreakdownTable = ({ plDimension, rows }) => {
  const colCfg = PL_COLUMNS[plDimension];
  const columns = useMemo(() => {
    const cols = [
      {
        key: colCfg?.key || "name",
        label: colCfg?.label || "Name",
        render: (row) => <span className="font-medium text-slate-700 truncate max-w-[200px] block">{row[colCfg?.key] || "—"}</span>,
      },
    ];
    if (plDimension === "job") {
      cols.push(
        { key: "billing_entity", label: "Customer", render: (row) => <span className="text-slate-500 truncate max-w-[160px] block">{row.billing_entity || "—"}</span> },
        { key: "withdrawal_count", label: "Orders", align: "right", render: (row) => <span className="tabular-nums text-slate-500">{row.withdrawal_count || row.transaction_count}</span> },
      );
    }
    cols.push(
      { key: "revenue", label: "Revenue", align: "right", render: (row) => <span className="tabular-nums font-semibold text-slate-900">{valueFormatter(row.revenue)}</span> },
      { key: "cost", label: "COGS", align: "right", render: (row) => <span className="tabular-nums text-slate-500">{valueFormatter(row.cost)}</span> },
      { key: "profit", label: "Profit", align: "right", render: (row) => <span className="tabular-nums font-semibold text-slate-900">{valueFormatter(row.profit)}</span> },
      {
        key: "margin_pct",
        label: "Margin",
        align: "right",
        render: (row) => {
          const isHigh = (row.margin_pct || 0) >= 40;
          const isLow = (row.margin_pct || 0) < 30;
          return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold tabular-nums ${isHigh ? "bg-emerald-50 text-emerald-700" : isLow ? "bg-orange-50 text-orange-700" : "bg-blue-50 text-blue-700"}`}>{row.margin_pct}%</span>;
        },
      },
    );
    return cols;
  }, [plDimension, colCfg]);

  const dataWithId = useMemo(() => rows.map((r, i) => ({ ...r, id: r[colCfg?.key] || i })), [rows, colCfg]);

  return (
    <DataTable
      data={dataWithId}
      columns={columns}
      title={`Breakdown — ${PL_DIMENSIONS.find((d) => d.value === plDimension)?.label || plDimension}`}
      emptyMessage="No P&L data"
      searchable
      exportable
      exportFilename={`pl-${plDimension}.csv`}
      pageSize={20}
    />
  );
};

const AR_AGING_COLUMNS = [
  { key: "billing_entity", label: "Entity", render: (row) => <span className="font-medium text-slate-700">{row.billing_entity}</span> },
  { key: "total_ar", label: "Total AR", align: "right", render: (row) => <span className="tabular-nums font-semibold">{valueFormatter(row.total_ar)}</span> },
  { key: "current_not_due", label: "Current", align: "right", render: (row) => <span className="tabular-nums text-slate-500">{valueFormatter(row.current_not_due)}</span> },
  { key: "overdue_1_30", label: "1–30d", align: "right", render: (row) => <span className="tabular-nums text-amber-500">{valueFormatter(row.overdue_1_30)}</span> },
  { key: "overdue_31_60", label: "31–60d", align: "right", render: (row) => <span className="tabular-nums text-amber-600">{valueFormatter(row.overdue_31_60)}</span> },
  { key: "overdue_61_90", label: "61–90d", align: "right", render: (row) => <span className="tabular-nums text-orange-600">{valueFormatter(row.overdue_61_90)}</span> },
  { key: "overdue_90_plus", label: "90d+", align: "right", render: (row) => <span className="tabular-nums text-red-600 font-semibold">{valueFormatter(row.overdue_90_plus)}</span> },
];

const ARAgingTable = ({ data }) => {
  const dataWithId = useMemo(() => data.map((r, i) => ({ ...r, id: r.billing_entity || i })), [data]);
  return (
    <DataTable
      data={dataWithId}
      columns={AR_AGING_COLUMNS}
      title="Accounts Receivable Aging"
      emptyMessage="No AR data"
      searchable
      exportable
      exportFilename="ar-aging.csv"
    />
  );
};

const Reports = () => {
  const [activeTab, setActiveTab] = useState("pl");
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [dateRange, setDateRange] = useState({ from: null, to: null });
  const [plDimension, setPlDimension] = useState("overall");

  const dateParams = useMemo(() => ({
    start_date: dateRange.from?.toISOString(),
    end_date: dateRange.to?.toISOString(),
  }), [dateRange]);

  const plParams = useMemo(() => ({ ...dateParams, group_by: plDimension }), [dateParams, plDimension]);

  const { data: plData, isLoading: plLoading } = useReportPL(plParams);
  const { data: arAging } = useReportArAging();
  const { data: salesReport, isLoading: salesLoading } = useReportSales(dateParams);
  const { data: inventoryReport, isLoading: invLoading } = useReportInventory();
  const { data: trendsReport, isLoading: trendsLoading } = useReportTrends({ ...dateParams, group_by: trendsGroupBy });
  const { data: marginsReport } = useReportMargins(dateParams);

  const margins = marginsReport?.products || [];

  const paymentChartData = salesReport?.by_payment_status
    ? Object.entries(salesReport.by_payment_status).map(([name, value]) => ({ name: name.charAt(0).toUpperCase() + name.slice(1), value: parseFloat(value.toFixed(2)) }))
    : [];

  const departmentChartData = inventoryReport?.by_department
    ? Object.entries(inventoryReport.by_department).map(([name, data]) => ({ name, count: data.count, value: parseFloat((data.retail_value || data.value || 0).toFixed(2)), cost: parseFloat((data.cost_value || data.cost || 0).toFixed(2)) }))
    : [];

  const handleExportCSV = () => {
    const rows = [];
    if (activeTab === "pl" && plData) {
      rows.push(["P&L Report", `Dimension: ${plDimension}`]);
      rows.push(["Revenue", plData.summary?.revenue]);
      rows.push(["COGS", plData.summary?.cogs]);
      rows.push(["Gross Profit", plData.summary?.gross_profit]);
      rows.push(["Margin %", plData.summary?.margin_pct]);
      if (plData.rows?.length > 0) {
        rows.push([]);
        const colCfg = PL_COLUMNS[plDimension];
        rows.push([colCfg?.label || "Name", "Revenue", "COGS", "Profit", "Margin %"]);
        plData.rows.forEach((r) => rows.push([r[colCfg?.key] || "—", r.revenue, r.cost, r.profit, r.margin_pct]));
      }
    } else if (activeTab === "sales" && salesReport) {
      rows.push(["Metric", "Value"]);
      rows.push(["Total Revenue", salesReport.total_revenue]);
      rows.push(["Total Transactions", salesReport.total_transactions]);
      if (salesReport.top_products?.length) { rows.push([]); rows.push(["Product", "Revenue", "Qty"]); salesReport.top_products.forEach((p) => rows.push([p.name, p.revenue, p.quantity])); }
    } else if (activeTab === "trends" && trendsReport) {
      rows.push(["Period", "Revenue", "Cost", "Profit"]);
      trendsReport.series?.forEach((r) => rows.push([r.date, r.revenue, r.cost, r.profit]));
    }
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `report-${activeTab}-${format(new Date(), "yyyy-MM-dd")}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  const inStock = (inventoryReport?.total_products || 0) - (inventoryReport?.low_stock_count || 0) - (inventoryReport?.out_of_stock_count || 0);
  const totalP = inventoryReport?.total_products || 1;

  const loading = plLoading && salesLoading && invLoading && trendsLoading;
  if (loading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="reports-page">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Reports</h1>
          <p className="text-slate-500 mt-1 text-sm">P&L, sales, inventory, and profit analytics</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
            {DATE_PRESETS.map((preset) => (
              <button key={preset.label} onClick={() => setDateRange(preset.getValue())} className="text-xs px-3 py-1.5 rounded-md text-slate-600 hover:bg-white hover:shadow-sm transition-all font-medium">{preset.label}</button>
            ))}
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2" data-testid="date-range-btn">
                <CalendarIcon className="w-4 h-4" />
                {dateRange.from ? dateRange.to ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}` : format(dateRange.from, "MMM d, yyyy") : "Custom"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end"><Calendar mode="range" selected={dateRange} onSelect={(r) => setDateRange(r || { from: null, to: null })} numberOfMonths={2} /></PopoverContent>
          </Popover>
          {(dateRange.from || dateRange.to) && <button onClick={() => setDateRange({ from: null, to: null })} className="text-xs text-slate-400 hover:text-slate-600">Clear</button>}
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-2" data-testid="export-csv-btn"><Download className="w-4 h-4" />Export</Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-transparent border-b border-slate-200 rounded-none p-0 h-auto gap-0 w-full justify-start" data-testid="report-tabs">
          {[
            { value: "pl", label: "P&L", icon: Receipt },
            { value: "sales", label: "Sales", icon: BarChart3 },
            { value: "inventory", label: "Inventory", icon: Package },
            { value: "trends", label: "Trends & Margins", icon: TrendingUp },
          ].map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-500 data-[state=active]:text-slate-900 text-slate-500 px-5 py-3 text-sm font-semibold gap-2 bg-transparent shadow-none" data-testid={`${value}-tab`}>
              <Icon className="w-4 h-4" />{label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* ══ P&L ════════════════════════════════════════════════════════════ */}
        <TabsContent value="pl" className="space-y-6 mt-6" data-testid="pl-report-content">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">View</span>
            <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
              {PL_DIMENSIONS.map((d) => (
                <button key={d.value} onClick={() => setPlDimension(d.value)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${plDimension === d.value ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"}`} data-testid={`pl-dim-${d.value}`}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {plData?.summary && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl p-6 text-white shadow-md">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-violet-100 mb-4">Revenue</p>
                <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(plData.summary.revenue)}</p>
              </div>
              <Stat label="COGS" value={valueFormatter(plData.summary.cogs)} icon={DollarSign} accent="orange" />
              <Stat label="Gross Profit" value={valueFormatter(plData.summary.gross_profit)} icon={TrendingUp} accent="emerald" note={`${plData.summary.margin_pct}% margin`} />
              {plData.summary.tax_collected != null && <Stat label="Tax Collected" value={valueFormatter(plData.summary.tax_collected)} icon={Receipt} accent="slate" />}
              {plData.summary.shrinkage != null && plData.summary.shrinkage > 0 && <Stat label="Shrinkage" value={valueFormatter(plData.summary.shrinkage)} icon={Package} accent="orange" note="inventory adjustments" />}
            </div>
          )}

          {plDimension !== "overall" && plData?.rows?.length > 0 && (
            <PLBreakdownTable plDimension={plDimension} rows={plData.rows} />
          )}

          {plDimension === "overall" && plData?.rows?.length === 0 && arAging?.length > 0 && (
            <ARAgingTable data={arAging} />
          )}

          {plDimension !== "overall" && (!plData?.rows || plData.rows.length === 0) && (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
              <Briefcase className="w-10 h-10 mx-auto text-slate-200 mb-3" />
              <p className="text-sm text-slate-400">No P&L data for this period and dimension</p>
            </div>
          )}
        </TabsContent>

        {/* ══ SALES ══════════════════════════════════════════════════════════ */}
        <TabsContent value="sales" className="space-y-6 mt-6" data-testid="sales-report-content">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="md:col-span-1 bg-gradient-to-br from-amber-500 to-orange-500 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(salesReport?.total_revenue || 0)}</p>
              <p className="text-xs text-amber-200 mt-3">{salesReport?.total_transactions || 0} transactions</p>
            </div>
            <Stat label="COGS" value={valueFormatter(salesReport?.total_cogs || 0)} icon={DollarSign} accent="orange" note="cost of goods sold" />
            <Stat label="Gross Profit" value={valueFormatter(salesReport?.gross_profit || 0)} icon={TrendingUp} accent="emerald" note={`${salesReport?.gross_margin_pct ?? 0}% margin`} />
            <Stat label="Avg Transaction" value={valueFormatter(salesReport?.average_transaction || 0)} accent="violet" note="per order" />
          </div>
          <Panel><SectionHead title="Sales by Payment Status" />{paymentChartData.length > 0 ? <PaymentStrip data={paymentChartData} /> : <p className="text-sm text-slate-400 py-8 text-center">No sales data</p>}</Panel>
          <Panel><SectionHead title="Top Selling Products" />{salesReport?.top_products?.length > 0 ? <ProductBars products={salesReport.top_products.slice(0, 10)} /> : <p className="text-sm text-slate-400 py-8 text-center">No sales data</p>}</Panel>
        </TabsContent>

        {/* ══ INVENTORY ══════════════════════════════════════════════════════ */}
        <TabsContent value="inventory" className="space-y-6 mt-6" data-testid="inventory-report-content">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Total Products" value={inventoryReport?.total_products || 0} icon={Package} accent="blue" />
            <Stat label="Retail Value" value={valueFormatter(inventoryReport?.total_retail_value || 0)} icon={DollarSign} accent="emerald" />
            <Stat label="Cost Value" value={valueFormatter(inventoryReport?.total_cost_value || 0)} icon={Layers} accent="slate" />
            <Stat label="Unrealized Margin" value={valueFormatter(inventoryReport?.unrealized_margin || inventoryReport?.potential_profit || 0)} note={inventoryReport?.margin_pct ? `${inventoryReport.margin_pct}%` : ""} icon={TrendingUp} accent="amber" />
          </div>
          <Panel>
            <SectionHead title="Stock Health" />
            <div className="flex h-5 rounded-lg overflow-hidden gap-px mb-3">
              <div className="bg-emerald-400" style={{ width: `${(inStock / totalP) * 100}%` }} />
              <div className="bg-orange-400" style={{ width: `${((inventoryReport?.low_stock_count || 0) / totalP) * 100}%` }} />
              <div className="bg-red-500" style={{ width: `${((inventoryReport?.out_of_stock_count || 0) / totalP) * 100}%` }} />
            </div>
            <div className="flex gap-5 text-xs">
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />In stock <strong className="tabular-nums">{inStock}</strong></span>
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-orange-400 inline-block" />Low <strong className="tabular-nums">{inventoryReport?.low_stock_count || 0}</strong></span>
              <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" />Out <strong className="tabular-nums">{inventoryReport?.out_of_stock_count || 0}</strong></span>
            </div>
          </Panel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel><SectionHead title="Value by Department" />{departmentChartData.length > 0 ? <DeptBars data={departmentChartData} /> : <p className="text-sm text-slate-400 py-8 text-center">No data</p>}</Panel>
            <Panel>
              <SectionHead title="Low Stock Alert" action={inventoryReport?.low_stock_items?.length > 0 && <span className="text-xs font-bold text-orange-500 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200">{inventoryReport.low_stock_count} items</span>} />
              {inventoryReport?.low_stock_items?.length > 0 ? <div className="max-h-[360px] overflow-auto -mx-6 px-6"><LowStockList items={inventoryReport.low_stock_items} /></div> : <p className="text-sm text-slate-400 py-8 text-center">All well stocked</p>}
            </Panel>
          </div>
        </TabsContent>

        {/* ══ TRENDS ═════════════════════════════════════════════════════════ */}
        <TabsContent value="trends" className="space-y-6 mt-6" data-testid="trends-report-content">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-100 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(trendsReport?.totals?.revenue || 0)}</p>
            </div>
            <Stat label="Total Cost (COGS)" value={valueFormatter(trendsReport?.totals?.cost || 0)} icon={DollarSign} accent="orange" />
            <Stat label="Gross Profit" value={valueFormatter(trendsReport?.totals?.profit || 0)} icon={TrendingUp} accent="blue" />
          </div>
          <Panel>
            <SectionHead title="Revenue, Cost & Profit Over Time" action={
              <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
                {["day", "week", "month"].map((g) => (
                  <button key={g} onClick={() => setTrendsGroupBy(g)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${trendsGroupBy === g ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"}`}>{g.charAt(0).toUpperCase() + g.slice(1)}</button>
                ))}
              </div>
            } />
            {trendsReport?.series?.length > 0 ? <AreaChart data={trendsReport.series} index="date" categories={["revenue", "cost", "profit"]} colors={["emerald", "orange", "blue"]} valueFormatter={valueFormatter} className="h-[280px] mt-2" /> : <div className="h-[280px] flex items-center justify-center"><p className="text-sm text-slate-400">No trend data</p></div>}
          </Panel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel><SectionHead title="Top Products by Revenue" />{margins.length > 0 ? <ProductBars products={margins.slice(0, 10).map((p) => ({ name: p.name, revenue: p.revenue, quantity: p.quantity }))} /> : <p className="text-sm text-slate-400 py-8 text-center">No data</p>}</Panel>
            <Panel>
              <SectionHead title="Profit Margin by Product" />
              <div className="flex items-center gap-4 mb-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-400 inline-block" />≥40%</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-400 inline-block" />30–40%</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-400 inline-block" />&lt;30%</span>
              </div>
              {margins.length > 0 ? <div className="max-h-[360px] overflow-auto -mx-6 px-6"><MarginList margins={margins} /></div> : <p className="text-sm text-slate-400 py-8 text-center">No data</p>}
            </Panel>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Reports;
