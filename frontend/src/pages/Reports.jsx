import { useState, useMemo } from "react";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  TrendingUp, Package, DollarSign, Calendar as CalendarIcon,
  Download, Layers, Briefcase, Receipt, ChevronDown, ChevronRight, Activity,
} from "lucide-react";
import { format } from "date-fns";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { DATE_PRESETS } from "@/lib/constants";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { StatCard } from "@/components/StatCard";
import {
  useReportSales, useReportInventory, useReportTrends, useReportMargins,
  useReportPL, useReportArAging, useReportKpis, useReportProductPerformance,
  useReportReorderUrgency, useReportProductActivity,
} from "@/hooks/useReports";
import { useFinancialSummary } from "@/hooks/useFinancials";
import { useProducts } from "@/hooks/useProducts";
import { HorizontalBarChart } from "@/components/charts/HorizontalBarChart";
import { MultiLineChart } from "@/components/charts/MultiLineChart";
import { GaugeRing } from "@/components/charts/GaugeRing";
import { ProductBubblePlot } from "@/components/charts/ProductBubblePlot";
import { LollipopChart } from "@/components/charts/LollipopChart";
import { WaterfallChart } from "@/components/charts/WaterfallChart";
import { DotColumnChart } from "@/components/charts/DotColumnChart";
import { ActivityHeatmap } from "@/components/charts/ActivityHeatmap";
import { ProductDetailModal } from "@/components/ProductDetailModal";
import { ChartExplainer, BubbleChartGuide } from "@/components/charts/ChartExplainer";
import { Panel, SectionHead as SectionHeadBase } from "@/components/Panel";
import {
  PaymentStrip, LowStockList, PL_DIMENSIONS, PLBreakdownTable, ARAgingTable, PLStatement, FinanceTab,
} from "@/components/reports/ReportHelpers";

const Stat = StatCard;
const SectionHead = ({ title, action }) => <SectionHeadBase title={title} action={action} variant="report" />;

const Reports = () => {
  const t = themeColors();
  const [activeTab, setActiveTab] = useState("pl");
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [dateRange, setDateRange] = useState({ from: null, to: null });
  const [plDimension, setPlDimension] = useState("overall");
  const [arAgingOpen, setArAgingOpen] = useState(true);
  const [selectedProduct, setSelectedProduct] = useState(null);

  const dateParams = useMemo(() => ({
    start_date: dateToISO(dateRange.from),
    end_date: endOfDayISO(dateRange.to),
  }), [dateRange]);

  const plParams = useMemo(() => ({ ...dateParams, group_by: plDimension }), [dateParams, plDimension]);

  const { data: plData, isLoading: plLoading } = useReportPL(plParams);
  const { data: arAging } = useReportArAging(dateParams);
  const { data: salesReport, isLoading: salesLoading } = useReportSales(dateParams);
  const { data: inventoryReport, isLoading: invLoading } = useReportInventory();
  const { data: trendsReport, isLoading: trendsLoading } = useReportTrends({ ...dateParams, group_by: trendsGroupBy });
  const { data: marginsReport } = useReportMargins(dateParams);
  const { data: kpis } = useReportKpis(dateParams);
  const { data: perfData } = useReportProductPerformance(dateParams);
  const { data: reorderData } = useReportReorderUrgency();

  const jobPlParams = useMemo(() => ({ ...dateParams, group_by: "job" }), [dateParams]);
  const contractorPlParams = useMemo(() => ({ ...dateParams, group_by: "contractor" }), [dateParams]);
  const { data: jobPlData } = useReportPL(jobPlParams);
  const { data: contractorPlData } = useReportPL(contractorPlParams);
  const { data: financialSummary } = useFinancialSummary(dateParams);

  const productPerf = perfData?.products || [];
  const reorderProducts = reorderData?.products || [];
  const lollipopData = useMemo(() => reorderProducts.map((p) => ({
    name: p.name,
    value: p.days_until_stockout,
    urgency: p.urgency,
    id: p.product_id,
    ...p,
  })), [reorderProducts]);

  const trailing365Params = useMemo(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 365);
    return { start_date: start.toISOString(), end_date: end.toISOString(), group_by: "day" };
  }, []);
  const { data: dailyTrends } = useReportTrends(trailing365Params);
  const dotColumnData = useMemo(() => {
    if (!dailyTrends?.series) return [];
    return dailyTrends.series.map((d) => ({ date: d.date, value: d.transaction_count || 0 }));
  }, [dailyTrends]);

  const handleProductClick = (product) => {
    setSelectedProduct({ id: product.product_id || product.id, name: product.name, sku: product.sku })
  };

  const [heatmapProductId, setHeatmapProductId] = useState(null);
  const { data: productsList } = useProducts();
  const activityParams = useMemo(() => ({ product_id: heatmapProductId || undefined }), [heatmapProductId]);
  const { data: productActivityData } = useReportProductActivity(activityParams);
  const productHeatmapData = useMemo(() => {
    if (!productActivityData?.series) return [];
    return productActivityData.series.map((d) => ({
      date: d.day,
      value: d.transaction_count || 0,
      units: d.units_moved || 0,
    }));
  }, [productActivityData]);

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
    } else if (activeTab === "operations" && salesReport) {
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

  const waterfallItems = useMemo(() => {
    if (!plData?.summary || plDimension !== "overall") return [];
    const s = plData.summary;
    const items = [{ label: "Revenue", value: s.revenue || 0, type: "total" }];
    if (s.cogs) items.push({ label: "COGS", value: -(s.cogs || 0), type: "decrease" });
    if (s.shrinkage) items.push({ label: "Shrinkage", value: -(s.shrinkage || 0), type: "decrease" });
    if (s.tax_collected) items.push({ label: "Tax", value: -(s.tax_collected || 0), type: "decrease" });
    const net = (s.revenue || 0) - (s.cogs || 0) - (s.shrinkage || 0) - (s.tax_collected || 0);
    items.push({ label: "Net Profit", value: net, type: "total" });
    return items;
  }, [plData, plDimension]);

  const loading = plLoading && salesLoading && invLoading && trendsLoading;
  if (loading) return <PageSkeleton />;

  return (
    <div className="p-8" data-testid="reports-page">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">Reports</h1>
          <p className="text-muted-foreground mt-1 text-sm">P&L, operations, inventory, and trend analytics</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
            {DATE_PRESETS.map((preset) => (
              <button key={preset.label} onClick={() => setDateRange(preset.getValue())} className="text-xs px-3 py-1.5 rounded-md text-muted-foreground hover:bg-card hover:shadow-sm transition-all font-medium">{preset.label}</button>
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
          {(dateRange.from || dateRange.to) && <button onClick={() => setDateRange({ from: null, to: null })} className="text-xs text-muted-foreground hover:text-foreground">Clear</button>}
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-2" data-testid="export-csv-btn"><Download className="w-4 h-4" />Export</Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-transparent border-b border-border rounded-none p-0 h-auto gap-0 w-full justify-start" data-testid="report-tabs">
          {[
            { value: "pl", label: "P&L", icon: Receipt },
            { value: "finance", label: "Finance", icon: DollarSign },
            { value: "operations", label: "Operations", icon: Activity },
            { value: "inventory", label: "Inventory", icon: Package },
            { value: "trends", label: "Trends", icon: TrendingUp },
          ].map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="rounded-none border-b-2 border-transparent data-[state=active]:border-accent data-[state=active]:text-foreground text-muted-foreground px-5 py-3 text-sm font-semibold gap-2 bg-transparent shadow-none" data-testid={`${value}-tab`}>
              <Icon className="w-4 h-4" />{label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* ══ P&L ════════════════════════════════════════════════════════════ */}
        <TabsContent value="pl" className="space-y-6 mt-6" data-testid="pl-report-content">
          {/* P&L Statement + Waterfall side by side */}
          {plDimension === "overall" && plData?.summary && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <PLStatement summary={plData.summary} />
              {waterfallItems.length > 0 && (
                <Panel>
                  <SectionHead title="P&L Waterfall" />
                  <ChartExplainer
                    title="Waterfall Chart"
                    bullets={[
                      "Starts with total Revenue on the left",
                      "Each red bar shows a deduction (COGS, shrinkage, tax) dropping from the running total",
                      "The final bar shows your Net Profit — what's left after all deductions",
                      "Taller red bars mean bigger cost drains to investigate",
                    ]}
                  >
                    <WaterfallChart items={waterfallItems} height={260} />
                  </ChartExplainer>
                </Panel>
              )}
            </div>
          )}

          {/* Financial trend — stepped lines */}
          {plDimension === "overall" && trendsReport?.series?.length > 0 && (
            <Panel>
              <SectionHead title="Revenue, Cost & Profit Over Time" action={
                <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
                  {["day", "week", "month"].map((g) => (
                    <button key={g} onClick={() => setTrendsGroupBy(g)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${trendsGroupBy === g ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}>{g.charAt(0).toUpperCase() + g.slice(1)}</button>
                  ))}
                </div>
              } />
              <MultiLineChart
                data={trendsReport.series}
                xKey="date"
                series={[
                  { key: "revenue", label: "Revenue", color: t.success },
                  { key: "cost", label: "Cost", color: t.category1 },
                  { key: "profit", label: "Profit", color: t.info },
                ]}
                valueFormatter={valueFormatter}
                height={280}
                stepped
                area
              />
            </Panel>
          )}

          {/* KPI metrics row */}
          {kpis && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Stat label="Inventory Turnover" value={`${kpis.inventory_turnover}×`} icon={Layers} accent="blue" note={`${kpis.period_days} day period`} />
              <Stat label="Days in Inventory" value={`${kpis.dio} days`} icon={Package} accent="slate" />
              <Stat label="Avg Transaction" value={valueFormatter(kpis.total_revenue / Math.max(kpis.total_units_sold, 1))} icon={DollarSign} accent="violet" note={`${kpis.total_units_sold} units sold`} />
            </div>
          )}

          {/* Dimension selector */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">View</span>
            <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
              {PL_DIMENSIONS.map((d) => (
                <button key={d.value} onClick={() => setPlDimension(d.value)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${plDimension === d.value ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`} data-testid={`pl-dim-${d.value}`}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* Non-overall: show stat cards + breakdown table */}
          {plDimension !== "overall" && plData?.summary && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-category-4 to-category-4/80 rounded-xl p-6 text-white shadow-md">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-category-4/80 mb-4">Revenue</p>
                <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(plData.summary.revenue)}</p>
              </div>
              <Stat label="COGS" value={valueFormatter(plData.summary.cogs)} icon={DollarSign} accent="orange" />
              <Stat label="Gross Profit" value={valueFormatter(plData.summary.gross_profit)} icon={TrendingUp} accent="emerald" note={`${plData.summary.margin_pct}% margin`} />
              {plData.summary.tax_collected != null && <Stat label="Tax Collected" value={valueFormatter(plData.summary.tax_collected)} icon={Receipt} accent="slate" />}
            </div>
          )}

          {plDimension !== "overall" && plData?.rows?.length > 0 && (
            <PLBreakdownTable plDimension={plDimension} rows={plData.rows} />
          )}

          {plDimension !== "overall" && (!plData?.rows || plData.rows.length === 0) && (
            <div className="bg-card border border-border rounded-xl p-12 text-center shadow-sm">
              <Briefcase className="w-10 h-10 mx-auto text-border mb-3" />
              <p className="text-sm text-muted-foreground">No P&L data for this period and dimension</p>
            </div>
          )}

          {/* AR Aging — permanent collapsible section */}
          {arAging?.length > 0 && (
            <div>
              <button
                onClick={() => setArAgingOpen(!arAgingOpen)}
                className="flex items-center gap-2 text-sm font-semibold text-foreground hover:text-foreground mb-3"
              >
                {arAgingOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                Accounts Receivable Aging
                <span className="text-xs font-normal text-muted-foreground">({arAging.length} entities)</span>
              </button>
              {arAgingOpen && <ARAgingTable data={arAging} />}
            </div>
          )}
        </TabsContent>

        {/* ══ FINANCE ═════════════════════════════════════════════════════════ */}
        <TabsContent value="finance" className="mt-6" data-testid="finance-report-content">
          <FinanceTab
            financialSummary={financialSummary}
            arAging={arAging}
            arAgingOpen={arAgingOpen}
            setArAgingOpen={setArAgingOpen}
          />
        </TabsContent>

        {/* ══ OPERATIONS ══════════════════════════════════════════════════════ */}
        <TabsContent value="operations" className="space-y-6 mt-6" data-testid="operations-report-content">
          {/* Sales summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="md:col-span-1 bg-gradient-to-br from-accent-gradient-from to-accent-gradient-to rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-accent-foreground/80 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(salesReport?.total_revenue || 0)}</p>
              <p className="text-xs text-accent-foreground/60 mt-3">{salesReport?.total_transactions || 0} transactions</p>
            </div>
            <Stat label="COGS" value={valueFormatter(salesReport?.total_cogs || 0)} icon={DollarSign} accent="orange" />
            <Stat label="Gross Profit" value={valueFormatter(salesReport?.gross_profit || 0)} icon={TrendingUp} accent="emerald" note={`${salesReport?.gross_margin_pct ?? 0}% margin`} />
            <Stat label="Avg Transaction" value={valueFormatter(salesReport?.average_transaction || 0)} accent="violet" note="per order" />
          </div>

          {/* Payment status strip */}
          {paymentChartData.length > 0 && (
            <Panel>
              <SectionHead title="Payment Status" />
              <PaymentStrip data={paymentChartData} />
            </Panel>
          )}

          {/* Job throughput + Contractor activity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel>
              <SectionHead title="Job Throughput — Top by Revenue" />
              {jobPlData?.rows?.length > 0 ? (
                <HorizontalBarChart
                  data={jobPlData.rows.slice(0, 12)}
                  categoryKey="job_id"
                  series={[
                    { key: "revenue", label: "Revenue", color: t.category1 },
                    { key: "cost", label: "COGS", color: t.mutedForeground },
                  ]}
                  valueFormatter={valueFormatter}
                  showLegend
                  height={Math.max(200, jobPlData.rows.slice(0, 12).length * 36)}
                />
              ) : <p className="text-sm text-muted-foreground py-8 text-center">No job data</p>}
            </Panel>
            <Panel>
              <SectionHead title="Contractor Activity — Top by Revenue" />
              {contractorPlData?.rows?.length > 0 ? (
                <HorizontalBarChart
                  data={contractorPlData.rows.slice(0, 12).map((r) => ({ ...r, name: r.name || r.company || r.contractor_id || "Unknown" }))}
                  categoryKey="name"
                  series={[{ key: "revenue", label: "Revenue", color: t.info }]}
                  valueFormatter={valueFormatter}
                  height={Math.max(200, contractorPlData.rows.slice(0, 12).length * 36)}
                />
              ) : <p className="text-sm text-muted-foreground py-8 text-center">No contractor data</p>}
            </Panel>
          </div>

          {/* Operational activity dot column */}
          {dotColumnData.length > 0 && (
            <Panel>
              <SectionHead title="Daily Operational Activity" action={
                <span className="text-xs text-muted-foreground tabular-nums">{dotColumnData.filter((d) => d.value > 0).length} active days</span>
              } />
              <ChartExplainer
                title="Activity Pattern"
                bullets={[
                  "Each dot is one day — columns are months",
                  "Darker/brighter dots = more transactions that day",
                  "Look for patterns: consistent activity, quiet periods, or spikes",
                  "Gaps or pale columns may indicate supply issues or seasonal slowdowns",
                ]}
              >
                <DotColumnChart data={dotColumnData} height={260} />
              </ChartExplainer>
            </Panel>
          )}
        </TabsContent>

        {/* ══ INVENTORY — Interactive Product Analytics ════════════════════ */}
        <TabsContent value="inventory" className="space-y-6 mt-6" data-testid="inventory-report-content">
          {/* Compact stat strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Total Products" value={inventoryReport?.total_products || 0} icon={Package} accent="blue" />
            <Stat label="Retail Value" value={valueFormatter(inventoryReport?.total_retail_value || 0)} icon={DollarSign} accent="emerald" />
            <Stat label="Cost Value" value={valueFormatter(inventoryReport?.total_cost_value || 0)} icon={Layers} accent="slate" />
            <Stat label="Unrealized Margin" value={valueFormatter(inventoryReport?.unrealized_margin || inventoryReport?.potential_profit || 0)} note={inventoryReport?.margin_pct ? `${inventoryReport.margin_pct}%` : ""} icon={TrendingUp} accent="amber" />
          </div>

          {/* Gauge rings row */}
          {kpis && (
            <ChartExplainer
              title="Health Gauges"
              position="top-left"
              bullets={[
                "Each gauge shows one key inventory health metric",
                "Green zone = healthy, Amber = needs watching, Red = action needed",
                "Turnover: how many times you sell through stock per period (higher is better)",
                "Sell-Through: % of stock that has been sold (higher = faster moving)",
                "Gross Margin: your profit % after cost of goods (higher = more profitable)",
              ]}
            >
              <div className="flex flex-wrap items-center justify-center gap-6">
                <div className="flex flex-col items-center">
                  <GaugeRing
                    value={kpis.inventory_turnover}
                    max={Math.max(kpis.inventory_turnover * 1.5, 6)}
                    label="Turnover"
                    unit="×"
                    zones={[{ max: 0.2, color: t.destructive }, { max: 0.5, color: t.warning }, { max: 1, color: t.success }]}
                    size={150}
                  />
                </div>
                <div className="flex flex-col items-center">
                  <GaugeRing
                    value={kpis.sell_through_pct}
                    max={100}
                    label="Sell-Through"
                    unit="%"
                    zones={[{ max: 0.3, color: t.destructive }, { max: 0.6, color: t.warning }, { max: 1, color: t.success }]}
                    size={150}
                  />
                </div>
                <div className="flex flex-col items-center">
                  <GaugeRing
                    value={kpis.gross_margin_pct}
                    max={100}
                    label="Gross Margin"
                    unit="%"
                    zones={[{ max: 0.3, color: t.destructive }, { max: 0.5, color: t.warning }, { max: 1, color: t.success }]}
                    size={150}
                  />
                </div>
              </div>
            </ChartExplainer>
          )}

          {/* Product Bubble Plot — centerpiece */}
          {productPerf.length > 0 && (
            <Panel>
              <SectionHead title="Product Portfolio — Sell-Through vs Margin" action={
                <span className="text-xs text-muted-foreground">{productPerf.length} products · click to drill in</span>
              } />
              <ChartExplainer
                title="Product Portfolio"
                wide
                content={<BubbleChartGuide />}
              >
                <ProductBubblePlot
                  products={productPerf}
                  onBubbleClick={handleProductClick}
                  height={420}
                />
              </ChartExplainer>
            </Panel>
          )}

          {/* Reorder Urgency + Department Value */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel>
              <SectionHead title="Reorder Urgency — Days to Stockout" action={
                lollipopData.length > 0 && <span className="text-xs font-bold text-destructive bg-destructive/10 px-2 py-0.5 rounded-full border border-destructive/30">{lollipopData.filter((d) => d.urgency === "critical" || d.urgency === "high").length} urgent</span>
              } />
              {lollipopData.length > 0 ? (
                <ChartExplainer
                  title="Reorder Urgency"
                  bullets={[
                    "Each dot is a product — fewer days = closer to running out",
                    "Red = critical (under 3 days), Orange = high (under 7 days)",
                    "Amber = medium (under 30 days), Green = healthy stock",
                    "Click any product to view details and adjust stock",
                    "Products at the top of the list need the most urgent attention",
                  ]}
                >
                  <LollipopChart
                    data={lollipopData.slice(0, 20)}
                    valueLabel="days"
                    onDotClick={handleProductClick}
                    height={Math.max(200, Math.min(lollipopData.length, 20) * 28)}
                  />
                </ChartExplainer>
              ) : <p className="text-sm text-muted-foreground py-8 text-center">All stock levels healthy</p>}
            </Panel>
            <Panel>
              <SectionHead title="Value by Department" />
              {departmentChartData.length > 0 ? (
                <HorizontalBarChart
                  data={departmentChartData}
                  categoryKey="name"
                  series={[
                    { key: "cost", label: "Cost", color: t.category5 },
                    { key: "value", label: "Retail", color: t.success },
                  ]}
                  valueFormatter={valueFormatter}
                  showLegend
                  height={Math.max(200, departmentChartData.length * 40)}
                />
              ) : <p className="text-sm text-muted-foreground py-8 text-center">No data</p>}
            </Panel>
          </div>

          {/* Product Activity Heatmap */}
          <Panel>
            <SectionHead
              title="Product Activity"
              action={
                <select
                  value={heatmapProductId || ""}
                  onChange={(e) => setHeatmapProductId(e.target.value || null)}
                  className="text-xs border border-border rounded-lg px-2.5 py-1.5 text-muted-foreground bg-card focus:outline-none focus:ring-1 focus:ring-accent/30 max-w-[220px] truncate"
                >
                  <option value="">All products</option>
                  {(productsList || []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
                  ))}
                </select>
              }
            />
            {productHeatmapData.length > 0 ? (
              <ChartExplainer
                title="Activity Heatmap"
                bullets={[
                  "Each square is one day — darker = more withdrawal transactions",
                  "Use the dropdown to filter by a specific product or view all",
                  "Hover over any square to see the exact count and units moved",
                  "Consistent color = steady demand. Gaps = periods with no withdrawals",
                ]}
              >
                <ActivityHeatmap
                  data={productHeatmapData}
                  label="withdrawals"
                  tooltipExtra={(d) => d?.units ? `Units moved: ${d.units}` : ""}
                />
              </ChartExplainer>
            ) : (
              <p className="text-sm text-muted-foreground py-6 text-center">No withdrawal activity found</p>
            )}
          </Panel>

          {/* Stock Health + Low Stock */}
          <Panel>
            <SectionHead title="Stock Health" />
            <div className="flex h-5 rounded-lg overflow-hidden gap-px mb-3">
              <div className="bg-success" style={{ width: `${(inStock / totalP) * 100}%` }} />
              <div className="bg-category-5" style={{ width: `${((inventoryReport?.low_stock_count || 0) / totalP) * 100}%` }} />
              <div className="bg-destructive" style={{ width: `${((inventoryReport?.out_of_stock_count || 0) / totalP) * 100}%` }} />
            </div>
            <div className="flex gap-5 text-xs">
              <span className="flex items-center gap-1.5 text-muted-foreground"><span className="w-2 h-2 rounded-full bg-success inline-block" />In stock <strong className="tabular-nums">{inStock}</strong></span>
              <span className="flex items-center gap-1.5 text-muted-foreground"><span className="w-2 h-2 rounded-full bg-category-5 inline-block" />Low <strong className="tabular-nums">{inventoryReport?.low_stock_count || 0}</strong></span>
              <span className="flex items-center gap-1.5 text-muted-foreground"><span className="w-2 h-2 rounded-full bg-destructive inline-block" />Out <strong className="tabular-nums">{inventoryReport?.out_of_stock_count || 0}</strong></span>
            </div>
          </Panel>

          {inventoryReport?.low_stock_items?.length > 0 && (
            <Panel>
              <SectionHead title="Low Stock Alert" action={<span className="text-xs font-bold text-category-5 bg-category-5/10 px-2 py-0.5 rounded-full border border-category-5/30">{inventoryReport.low_stock_count} items</span>} />
              <div className="max-h-[360px] overflow-auto -mx-6 px-6"><LowStockList items={inventoryReport.low_stock_items} /></div>
            </Panel>
          )}
        </TabsContent>

        {/* ══ TRENDS ═════════════════════════════════════════════════════════ */}
        <TabsContent value="trends" className="space-y-6 mt-6" data-testid="trends-report-content">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-success to-success/80 rounded-xl p-6 text-white shadow-md">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-success/80 mb-4">Total Revenue</p>
              <p className="text-4xl font-bold tabular-nums leading-none">{valueFormatter(trendsReport?.totals?.revenue || 0)}</p>
            </div>
            <Stat label="Total Cost (COGS)" value={valueFormatter(trendsReport?.totals?.cost || 0)} icon={DollarSign} accent="orange" />
            <Stat label="Gross Profit" value={valueFormatter(trendsReport?.totals?.profit || 0)} icon={TrendingUp} accent="blue" />
          </div>

          <Panel>
            <SectionHead title="Revenue, Cost & Profit Over Time" action={
              <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
                {["day", "week", "month"].map((g) => (
                  <button key={g} onClick={() => setTrendsGroupBy(g)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${trendsGroupBy === g ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}>{g.charAt(0).toUpperCase() + g.slice(1)}</button>
                ))}
              </div>
            } />
            {trendsReport?.series?.length > 0 ? (
              <MultiLineChart
                data={trendsReport.series}
                xKey="date"
                series={[
                  { key: "revenue", label: "Revenue", color: t.success },
                  { key: "cost", label: "Cost", color: t.category1 },
                  { key: "profit", label: "Profit", color: t.info },
                ]}
                valueFormatter={valueFormatter}
                height={300}
                stepped
              />
            ) : <div className="h-[300px] flex items-center justify-center"><p className="text-sm text-muted-foreground">No trend data</p></div>}
          </Panel>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel>
              <SectionHead title="Top Products by Revenue" />
              {margins.length > 0 ? (
                <HorizontalBarChart
                  data={margins.slice(0, 10).map((p) => ({ name: p.name || p.product_id, revenue: p.revenue }))}
                  categoryKey="name"
                  series={[{ key: "revenue", label: "Revenue", color: t.category1 }]}
                  valueFormatter={valueFormatter}
                  height={Math.max(200, Math.min(margins.length, 10) * 36)}
                />
              ) : <p className="text-sm text-muted-foreground py-8 text-center">No data</p>}
            </Panel>
            <Panel>
              <SectionHead title="Product Performance — Revenue vs Margin" />
              {productPerf.length > 0 ? (
                <ChartExplainer
                  title="Product Scatter"
                  bullets={[
                    "Each bubble is a product — bigger = more revenue",
                    "Right = high sell-through, Top = high margin",
                    "Click any bubble to see full product details",
                  ]}
                >
                  <ProductBubblePlot
                    products={productPerf}
                    onBubbleClick={handleProductClick}
                    height={Math.max(300, 340)}
                  />
                </ChartExplainer>
              ) : <p className="text-sm text-muted-foreground py-8 text-center">No data</p>}
            </Panel>
          </div>
        </TabsContent>
      </Tabs>

      <ProductDetailModal
        product={selectedProduct}
        open={!!selectedProduct}
        onOpenChange={(open) => !open && setSelectedProduct(null)}
      />
    </div>
  );
};

export default Reports;
