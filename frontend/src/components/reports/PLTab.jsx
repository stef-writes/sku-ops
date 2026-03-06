import { useState, useMemo, useCallback } from "react";
import {
  TrendingUp, DollarSign, Layers, Package, Briefcase, Receipt,
  ChevronDown, ChevronRight, X,
} from "lucide-react";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { StatCard } from "@/components/StatCard";
import { useReportPL, useReportTrends, useReportKpis, useReportArAging } from "@/hooks/useReports";
import { MultiLineChart } from "@/components/charts/MultiLineChart";
import { WaterfallChart } from "@/components/charts/WaterfallChart";
import { ChartExplainer } from "@/components/charts/ChartExplainer";
import { Panel, SectionHead as SectionHeadBase } from "@/components/Panel";
import { PL_DIMENSIONS, PLBreakdownTable, ARAgingTable, PLStatement } from "./ReportHelpers";

const Stat = StatCard;
const SectionHead = ({ title, action }) => <SectionHeadBase title={title} action={action} variant="report" />;

const DIMENSION_FILTER_KEY = {
  job: "job_id",
  department: "department",
  entity: "billing_entity",
};

function ItemCard({ row, labelKey, dimension }) {
  const label = row[labelKey] || "—";
  const revenue = row.revenue || 0;
  const cost = row.cost || 0;
  const profit = row.profit ?? revenue - cost;
  const margin = row.margin_pct ?? (revenue > 0 ? ((profit / revenue) * 100).toFixed(1) : 0);
  const marginNum = parseFloat(margin);
  const badgeCls = marginNum >= 40
    ? "bg-success/10 text-success"
    : marginNum < 30
      ? "bg-category-5/10 text-category-5"
      : "bg-info/10 text-info";

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground truncate" title={label}>{label}</h3>
        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${badgeCls}`}>
          {margin}%
        </span>
      </div>
      {dimension === "job" && row.billing_entity && (
        <p className="text-xs text-muted-foreground mb-2 truncate">{row.billing_entity}</p>
      )}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">Revenue</span>
          <span className="tabular-nums font-semibold text-foreground">{valueFormatter(revenue)}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">COGS</span>
          <span className="tabular-nums text-muted-foreground">{valueFormatter(cost)}</span>
        </div>
        <div className="border-t border-border/50 my-1" />
        <div className="flex justify-between text-xs">
          <span className="font-semibold text-foreground">Profit</span>
          <span className={`tabular-nums font-bold ${profit >= 0 ? "text-success" : "text-destructive"}`}>
            {valueFormatter(profit)}
          </span>
        </div>
      </div>
      {(row.withdrawal_count || row.transaction_count) && (
        <p className="text-[10px] text-muted-foreground mt-2 tabular-nums">
          {row.withdrawal_count || row.transaction_count} orders
        </p>
      )}
    </div>
  );
}

const LABEL_KEYS = {
  job: "job_id",
  department: "department",
  entity: "billing_entity",
  product: "name",
};

export function PLTab({ reportFilters, dateParams }) {
  const t = themeColors();
  const [plDimension, setPlDimension] = useState("overall");
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [arAgingOpen, setArAgingOpen] = useState(true);

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedDepartment, setSelectedDepartment] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);

  const activeDrillLabel = selectedJobId || selectedDepartment || selectedEntity || null;
  const activeDrillDimension = selectedJobId ? "Job" : selectedDepartment ? "Department" : selectedEntity ? "Entity" : null;

  const clearDrill = useCallback(() => {
    setSelectedJobId(null);
    setSelectedDepartment(null);
    setSelectedEntity(null);
  }, []);

  const handleDimensionChange = useCallback((dim) => {
    setPlDimension(dim);
    clearDrill();
  }, [clearDrill]);

  const drillFilters = useMemo(() => ({
    ...reportFilters,
    job_id: selectedJobId || reportFilters.job_id,
    department: selectedDepartment || reportFilters.department,
    billing_entity: selectedEntity || reportFilters.billing_entity,
  }), [reportFilters, selectedJobId, selectedDepartment, selectedEntity]);

  const plParams = useMemo(() => ({ ...drillFilters, group_by: plDimension }), [drillFilters, plDimension]);
  const { data: plData } = useReportPL(plParams);
  const { data: trendsReport } = useReportTrends({ ...drillFilters, group_by: trendsGroupBy });
  const { data: kpis } = useReportKpis(drillFilters);
  const { data: arAging } = useReportArAging(dateParams);

  const handleRowDrill = useCallback((row) => {
    if (plDimension === "job" && row.job_id) setSelectedJobId(row.job_id);
    else if (plDimension === "department" && row.department) setSelectedDepartment(row.department);
    else if (plDimension === "entity" && row.billing_entity) setSelectedEntity(row.billing_entity);
  }, [plDimension]);

  const waterfallItems = useMemo(() => {
    if (!plData?.summary) return [];
    const s = plData.summary;
    const items = [{ label: "Revenue", value: s.revenue || 0, type: "total" }];
    if (s.cogs) items.push({ label: "COGS", value: -(s.cogs || 0), type: "decrease" });
    if (plDimension === "overall" && !activeDrillLabel) {
      if (s.shrinkage) items.push({ label: "Shrinkage", value: -(s.shrinkage || 0), type: "decrease" });
      if (s.tax_collected) items.push({ label: "Tax", value: -(s.tax_collected || 0), type: "decrease" });
    }
    const net = (plDimension === "overall" && !activeDrillLabel)
      ? (s.revenue || 0) - (s.cogs || 0) - (s.shrinkage || 0) - (s.tax_collected || 0)
      : s.gross_profit || ((s.revenue || 0) - (s.cogs || 0));
    items.push({ label: (plDimension === "overall" && !activeDrillLabel) ? "Net Profit" : "Gross Profit", value: net, type: "total" });
    return items;
  }, [plData, plDimension, activeDrillLabel]);

  const labelKey = LABEL_KEYS[plDimension];
  const rows = plData?.rows || [];
  const showItemizedCards = plDimension !== "overall" && plDimension !== "product" && rows.length > 0 && !activeDrillLabel;

  return (
    <div className="space-y-6">
      {/* Dimension selector */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">View</span>
        <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
          {PL_DIMENSIONS.map((d) => (
            <button key={d.value} onClick={() => handleDimensionChange(d.value)} className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${plDimension === d.value ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`} data-testid={`pl-dim-${d.value}`}>
              {d.label}
            </button>
          ))}
        </div>
        {activeDrillLabel && (
          <button onClick={clearDrill} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 transition-colors">
            {activeDrillDimension}: {activeDrillLabel}
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* ─── ITEMIZED CARDS for job/department/entity ─── */}
      {showItemizedCards && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">
              {rows.length} {plDimension === "job" ? "Jobs" : plDimension === "department" ? "Departments" : "Entities"} — P&L Breakdown
            </h2>
            <p className="text-xs text-muted-foreground">Click any card for full detail</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {rows.map((row, i) => (
              <button
                key={row[labelKey] || i}
                onClick={() => handleRowDrill(row)}
                className="text-left w-full"
              >
                <ItemCard row={row} labelKey={labelKey} dimension={plDimension} />
              </button>
            ))}
          </div>
        </>
      )}

      {/* ─── PRODUCT breakdown uses table (no item cards) ─── */}
      {plDimension === "product" && rows.length > 0 && !activeDrillLabel && (
        <PLBreakdownTable plDimension={plDimension} rows={rows} />
      )}

      {plDimension !== "overall" && rows.length === 0 && (
        <div className="bg-card border border-border rounded-xl p-12 text-center shadow-sm">
          <Briefcase className="w-10 h-10 mx-auto text-border mb-3" />
          <p className="text-sm text-muted-foreground">No P&L data for this period and dimension</p>
        </div>
      )}

      {/* ─── DETAIL VIEW (overall or drilled into a specific item) ─── */}
      {(plDimension === "overall" || activeDrillLabel) && plData?.summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Revenue" value={valueFormatter(plData.summary.revenue)} icon={DollarSign} accent="blue" />
            <Stat label="COGS" value={valueFormatter(plData.summary.cogs)} icon={DollarSign} accent="orange" />
            <Stat label="Gross Profit" value={valueFormatter(plData.summary.gross_profit)} icon={TrendingUp} accent="emerald" note={`${plData.summary.margin_pct}% margin`} />
            {plData.summary.tax_collected != null && plData.summary.tax_collected > 0
              ? <Stat label="Tax Collected" value={valueFormatter(plData.summary.tax_collected)} icon={Receipt} accent="slate" />
              : <Stat label="Margin" value={`${plData.summary.margin_pct}%`} icon={TrendingUp} accent="violet" />
            }
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PLStatement summary={plData.summary} />
            {waterfallItems.length > 0 && (
              <Panel>
                <SectionHead title="P&L Waterfall" />
                <ChartExplainer title="Waterfall Chart" bullets={["Starts with total Revenue on the left", "Each red bar shows a deduction dropping from the running total", "The final bar shows what's left after all deductions", "Taller red bars mean bigger cost drains to investigate"]}>
                  <WaterfallChart items={waterfallItems} height={260} />
                </ChartExplainer>
              </Panel>
            )}
          </div>
        </>
      )}

      {/* Revenue, Cost & Profit time-series */}
      {trendsReport?.series?.length > 0 && (
        <Panel>
          <SectionHead title={activeDrillLabel ? `Revenue, Cost & Profit — ${activeDrillLabel}` : "Revenue, Cost & Profit Over Time"} action={
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
              { key: "revenue", label: "Revenue", color: t.info },
              { key: "cost", label: "Cost", color: t.destructive },
              { key: "profit", label: "Profit", color: t.success, width: 3 },
            ]}
            valueFormatter={valueFormatter}
            height={280}
            stepped
          />
        </Panel>
      )}

      {/* KPI metrics — overall only */}
      {plDimension === "overall" && !activeDrillLabel && kpis && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Stat label="Inventory Turnover" value={`${kpis.inventory_turnover}×`} icon={Layers} accent="blue" note={`${kpis.period_days} day period`} />
          <Stat label="Days in Inventory" value={`${kpis.dio} days`} icon={Package} accent="slate" />
          <Stat label="Avg Transaction" value={valueFormatter(kpis.total_revenue / Math.max(kpis.total_units_sold, 1))} icon={DollarSign} accent="violet" note={`${kpis.total_units_sold} units sold`} />
        </div>
      )}

      {/* AR Aging */}
      {arAging?.length > 0 && (
        <div>
          <button onClick={() => setArAgingOpen(!arAgingOpen)} className="flex items-center gap-2 text-sm font-semibold text-foreground hover:text-foreground mb-3">
            {arAgingOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            Accounts Receivable Aging
            <span className="text-xs font-normal text-muted-foreground">({arAging.length} entities)</span>
          </button>
          {arAgingOpen && <ARAgingTable data={arAging} />}
        </div>
      )}
    </div>
  );
}
