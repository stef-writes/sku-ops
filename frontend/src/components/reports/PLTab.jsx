import { useState, useMemo, useCallback } from "react";
import {
  TrendingUp,
  DollarSign,
  Layers,
  Package,
  Briefcase,
  Receipt,
  ChevronDown,
  ChevronRight,
  X,
} from "lucide-react";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { StatCard } from "@/components/StatCard";
import { useReportPL, useReportTrends, useReportKpis, useReportArAging } from "@/hooks/useReports";
import { MultiLineChart } from "@/components/charts/MultiLineChart";
import { WaterfallChart } from "@/components/charts/WaterfallChart";
import { ChartExplainer } from "@/components/charts/ChartExplainer";
import { ReportPanel, ReportSectionHead } from "@/components/ReportPanel";
import { PL_DIMENSIONS, PLBreakdownTable, ARAgingTable, PLStatement } from "./ReportHelpers";

const Stat = StatCard;
const SectionHead = ({ title, action }) => <ReportSectionHead title={title} action={action} />;

export function PLTab({ reportFilters, dateParams }) {
  const t = themeColors();
  const [plDimension, setPlDimension] = useState("overall");
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [arAgingOpen, setArAgingOpen] = useState(true);

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedDepartment, setSelectedDepartment] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);

  const activeDrillLabel = selectedJobId || selectedDepartment || selectedEntity || null;
  const activeDrillDimension = selectedJobId
    ? "Job"
    : selectedDepartment
      ? "Department"
      : selectedEntity
        ? "Entity"
        : null;

  const clearDrill = useCallback(() => {
    setSelectedJobId(null);
    setSelectedDepartment(null);
    setSelectedEntity(null);
  }, []);

  const handleDimensionChange = useCallback(
    (dim) => {
      setPlDimension(dim);
      clearDrill();
    },
    [clearDrill],
  );

  const drillFilters = useMemo(
    () => ({
      ...reportFilters,
      job_id: selectedJobId || reportFilters.job_id,
      department: selectedDepartment || reportFilters.department,
      billing_entity: selectedEntity || reportFilters.billing_entity,
    }),
    [reportFilters, selectedJobId, selectedDepartment, selectedEntity],
  );

  const plParams = useMemo(
    () => ({ ...drillFilters, group_by: plDimension }),
    [drillFilters, plDimension],
  );
  const { data: plData } = useReportPL(plParams);
  const { data: trendsReport } = useReportTrends({
    ...drillFilters,
    group_by: trendsGroupBy,
  });
  const { data: kpis } = useReportKpis(drillFilters);
  const { data: arAging } = useReportArAging(dateParams);

  const handleRowDrill = useCallback(
    (row) => {
      if (plDimension === "job" && row.job_id) setSelectedJobId(row.job_id);
      else if (plDimension === "department" && row.department)
        setSelectedDepartment(row.department);
      else if (plDimension === "entity" && row.billing_entity)
        setSelectedEntity(row.billing_entity);
    },
    [plDimension],
  );

  const waterfallItems = useMemo(() => {
    if (!plData?.summary) return [];
    const s = plData.summary;
    const items = [{ label: "Revenue", value: s.revenue || 0, type: "total" }];
    if (s.cogs) items.push({ label: "COGS", value: -(s.cogs || 0), type: "decrease" });
    if (plDimension === "overall" && !activeDrillLabel) {
      if (s.shrinkage)
        items.push({
          label: "Shrinkage",
          value: -(s.shrinkage || 0),
          type: "decrease",
        });
      if (s.tax_collected)
        items.push({
          label: "Tax",
          value: -(s.tax_collected || 0),
          type: "decrease",
        });
    }
    const net =
      plDimension === "overall" && !activeDrillLabel
        ? (s.revenue || 0) - (s.cogs || 0) - (s.shrinkage || 0) - (s.tax_collected || 0)
        : s.gross_profit || (s.revenue || 0) - (s.cogs || 0);
    items.push({
      label: plDimension === "overall" && !activeDrillLabel ? "Net Profit" : "Gross Profit",
      value: net,
      type: "total",
    });
    return items;
  }, [plData, plDimension, activeDrillLabel]);

  const rows = plData?.rows || [];
  const showBreakdownTable = plDimension !== "overall" && rows.length > 0 && !activeDrillLabel;

  return (
    <div className="space-y-6">
      {/* Dimension selector */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
          View
        </span>
        <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
          {PL_DIMENSIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => handleDimensionChange(d.value)}
              className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${plDimension === d.value ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              data-testid={`pl-dim-${d.value}`}
            >
              {d.label}
            </button>
          ))}
        </div>
        {activeDrillLabel && (
          <button
            onClick={clearDrill}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 transition-colors"
          >
            {activeDrillDimension}: {activeDrillLabel}
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* ─── Breakdown table for job/department/entity/product ─── */}
      {showBreakdownTable && (
        <PLBreakdownTable
          plDimension={plDimension}
          rows={rows}
          onRowClick={plDimension !== "product" ? handleRowDrill : undefined}
          selectedId={activeDrillLabel}
          totalRows={plData?.total_rows}
        />
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
            <Stat
              label="Revenue"
              value={valueFormatter(plData.summary.revenue)}
              icon={DollarSign}
              accent="blue"
            />
            <Stat
              label="COGS"
              value={valueFormatter(plData.summary.cogs)}
              icon={DollarSign}
              accent="orange"
            />
            <Stat
              label="Gross Profit"
              value={valueFormatter(plData.summary.gross_profit)}
              icon={TrendingUp}
              accent="emerald"
              note={`${plData.summary.margin_pct}% margin`}
            />
            {plData.summary.tax_collected != null && plData.summary.tax_collected > 0 ? (
              <Stat
                label="Tax Collected"
                value={valueFormatter(plData.summary.tax_collected)}
                icon={Receipt}
                accent="slate"
              />
            ) : (
              <Stat
                label="Margin"
                value={`${plData.summary.margin_pct}%`}
                icon={TrendingUp}
                accent="violet"
              />
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PLStatement summary={plData.summary} />
            {waterfallItems.length > 0 && (
              <ReportPanel>
                <SectionHead title="P&L Waterfall" />
                <ChartExplainer
                  title="Waterfall Chart"
                  bullets={[
                    "Starts with total Revenue on the left",
                    "Each red bar shows a deduction dropping from the running total",
                    "The final bar shows what's left after all deductions",
                    "Taller red bars mean bigger cost drains to investigate",
                  ]}
                >
                  <WaterfallChart items={waterfallItems} height={260} />
                </ChartExplainer>
              </ReportPanel>
            )}
          </div>
        </>
      )}

      {/* Revenue, Cost & Profit time-series */}
      {trendsReport?.series?.length > 0 && (
        <ReportPanel>
          <SectionHead
            title={
              activeDrillLabel
                ? `Revenue, Cost & Profit — ${activeDrillLabel}`
                : "Revenue, Cost & Profit Over Time"
            }
            action={
              <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
                {["day", "week", "month"].map((g) => (
                  <button
                    key={g}
                    onClick={() => setTrendsGroupBy(g)}
                    className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all ${trendsGroupBy === g ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {g.charAt(0).toUpperCase() + g.slice(1)}
                  </button>
                ))}
              </div>
            }
          />
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
        </ReportPanel>
      )}

      {/* KPI metrics — overall only */}
      {plDimension === "overall" && !activeDrillLabel && kpis && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Stat
            label="Inventory Turnover"
            value={`${kpis.inventory_turnover}×`}
            icon={Layers}
            accent="blue"
            note={`${kpis.period_days} day period`}
          />
          <Stat
            label="Days in Inventory"
            value={`${kpis.dio} days`}
            icon={Package}
            accent="slate"
          />
          <Stat
            label="Avg Transaction"
            value={valueFormatter(kpis.total_revenue / Math.max(kpis.total_units_sold, 1))}
            icon={DollarSign}
            accent="violet"
            note={`${kpis.total_units_sold} units sold`}
          />
        </div>
      )}

      {/* AR Aging */}
      {arAging?.length > 0 && (
        <div>
          <button
            onClick={() => setArAgingOpen(!arAgingOpen)}
            className="flex items-center gap-2 text-sm font-semibold text-foreground hover:text-foreground mb-3"
          >
            {arAgingOpen ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
            Accounts Receivable Aging
            <span className="text-xs font-normal text-muted-foreground">
              ({arAging.length} entities)
            </span>
          </button>
          {arAgingOpen && <ARAgingTable data={arAging} />}
        </div>
      )}
    </div>
  );
}
