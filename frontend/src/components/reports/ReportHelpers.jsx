import { useMemo } from "react";
import { Building2, ChevronDown, ChevronRight } from "lucide-react";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { DataTable } from "@/components/DataTable";
import { StatCard } from "@/components/StatCard";
import { StackedBarChart } from "@/components/charts/StackedBarChart";
import { Panel, SectionHead as SectionHeadBase } from "@/components/Panel";

export const PaymentStrip = ({ data = [] }) => {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const t = themeColors();
  const palette = { Paid: t.success, Invoiced: t.info, Unpaid: t.category5, Unknown: t.mutedForeground };
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden gap-px mb-3">
        {data.map((d) => <div key={d.name} style={{ width: `${(d.value / total) * 100}%`, backgroundColor: palette[d.name] || t.mutedForeground }} title={`${d.name}: ${valueFormatter(d.value)}`} />)}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: palette[d.name] || t.mutedForeground }} />
            <span className="text-xs text-muted-foreground">{d.name}</span>
            <span className="text-xs font-bold text-foreground tabular-nums">{valueFormatter(d.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const LowStockList = ({ items = [] }) => (
  <div className="divide-y divide-border/50">
    {items.map((item, i) => {
      const pct = item.min_stock > 0 ? Math.min((item.quantity / item.min_stock) * 100, 100) : 0;
      const isEmpty = item.quantity === 0;
      return (
        <div key={i} className="py-3 flex items-center gap-3">
          <div className={`w-1.5 h-8 rounded-full shrink-0 ${isEmpty ? "bg-destructive" : "bg-category-5"}`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1">
              <p className="text-sm font-medium text-foreground truncate">{item.name}</p>
              <span className={`text-sm font-bold tabular-nums ml-3 shrink-0 ${isEmpty ? "text-destructive" : "text-category-5"}`}>{item.quantity} left</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${isEmpty ? "bg-destructive" : "bg-category-5"}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[10px] text-muted-foreground w-16 text-right shrink-0 tabular-nums">min {item.min_stock}</span>
            </div>
          </div>
        </div>
      );
    })}
  </div>
);

export const PL_DIMENSIONS = [
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
  product: { label: "Product", key: "name" },
};

export const PLBreakdownTable = ({ plDimension, rows, onRowClick, selectedId }) => {
  const colCfg = PL_COLUMNS[plDimension];
  const columns = useMemo(() => {
    const cols = [
      {
        key: colCfg?.key || "name",
        label: colCfg?.label || "Name",
        render: (row) => (
          <span className="font-medium text-foreground truncate max-w-[200px] block">
            {onRowClick && <span className="text-accent mr-1">&#x25B8;</span>}
            {row[colCfg?.key] || "\u2014"}
          </span>
        ),
      },
    ];
    if (plDimension === "job") {
      cols.push(
        { key: "billing_entity", label: "Customer", render: (row) => <span className="text-muted-foreground truncate max-w-[160px] block">{row.billing_entity || "\u2014"}</span> },
        { key: "withdrawal_count", label: "Orders", align: "right", render: (row) => <span className="tabular-nums text-muted-foreground">{row.withdrawal_count || row.transaction_count}</span> },
      );
    }
    cols.push(
      { key: "revenue", label: "Revenue", align: "right", render: (row) => <span className="tabular-nums font-semibold text-foreground">{valueFormatter(row.revenue)}</span> },
      { key: "cost", label: "COGS", align: "right", render: (row) => <span className="tabular-nums text-muted-foreground">{valueFormatter(row.cost)}</span> },
      { key: "profit", label: "Profit", align: "right", render: (row) => <span className="tabular-nums font-semibold text-foreground">{valueFormatter(row.profit)}</span> },
      {
        key: "margin_pct",
        label: "Margin",
        align: "right",
        render: (row) => {
          const isHigh = (row.margin_pct || 0) >= 40;
          const isLow = (row.margin_pct || 0) < 30;
          return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold tabular-nums ${isHigh ? "bg-success/10 text-success" : isLow ? "bg-category-5/10 text-category-5" : "bg-info/10 text-info"}`}>{row.margin_pct}%</span>;
        },
      },
    );
    return cols;
  }, [plDimension, colCfg]);

  const dataWithId = useMemo(() => rows.map((r, i) => ({ ...r, id: r[colCfg?.key] || i })), [rows, colCfg]);
  const selectedSet = useMemo(() => selectedId ? new Set([selectedId]) : new Set(), [selectedId]);

  return (
    <DataTable
      data={dataWithId}
      columns={columns}
      title={`Breakdown \u2014 ${PL_DIMENSIONS.find((d) => d.value === plDimension)?.label || plDimension}`}
      emptyMessage="No P&L data"
      searchable
      exportable
      exportFilename={`pl-${plDimension}.csv`}
      pageSize={20}
      onRowClick={onRowClick}
      selectedIds={selectedSet}
    />
  );
};

const AR_AGING_COLUMNS = [
  { key: "billing_entity", label: "Entity", render: (row) => <span className="font-medium text-foreground">{row.billing_entity}</span> },
  { key: "total_ar", label: "Total AR", align: "right", render: (row) => <span className="tabular-nums font-semibold">{valueFormatter(row.total_ar)}</span> },
  { key: "current_not_due", label: "Current", align: "right", render: (row) => <span className="tabular-nums text-muted-foreground">{valueFormatter(row.current_not_due)}</span> },
  { key: "overdue_1_30", label: "1\u201330d", align: "right", render: (row) => <span className="tabular-nums text-accent">{valueFormatter(row.overdue_1_30)}</span> },
  { key: "overdue_31_60", label: "31\u201360d", align: "right", render: (row) => <span className="tabular-nums text-accent">{valueFormatter(row.overdue_31_60)}</span> },
  { key: "overdue_61_90", label: "61\u201390d", align: "right", render: (row) => <span className="tabular-nums text-category-5">{valueFormatter(row.overdue_61_90)}</span> },
  { key: "overdue_90_plus", label: "90d+", align: "right", render: (row) => <span className="tabular-nums text-destructive font-semibold">{valueFormatter(row.overdue_90_plus)}</span> },
];

export const ARAgingTable = ({ data }) => {
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

const SectionHead = ({ title, action }) => <SectionHeadBase title={title} action={action} variant="report" />;

export const FinanceTab = ({ financialSummary, arAging, arAgingOpen, setArAgingOpen }) => {
  const t = themeColors();
  const arAgingByEntity = useMemo(() => {
    if (!arAging) return {};
    const map = {};
    for (const row of arAging) map[row.billing_entity] = row;
    return map;
  }, [arAging]);

  return (
    <div className="space-y-6">
      {financialSummary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard label="Total Revenue" value={valueFormatter(financialSummary.total_revenue || 0)} accent="emerald" />
          <StatCard label="Gross Margin" value={valueFormatter(financialSummary.gross_margin || 0)} accent="violet" />
          <StatCard label="Total Cost" value={valueFormatter(financialSummary.total_cost || 0)} accent="orange" />
          <StatCard label="Transactions" value={financialSummary.transaction_count || 0} accent="blue" />
        </div>
      )}

      {financialSummary?.by_billing_entity && Object.keys(financialSummary.by_billing_entity).length > 0 && (
        <Panel>
          <SectionHead title="By Billing Entity" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(financialSummary.by_billing_entity).map(([entity, data]) => {
              const aging = arAgingByEntity[entity];
              const hasOverdue90 = aging && ((aging.overdue_61_90 || 0) > 0 || (aging.overdue_90_plus || 0) > 0);
              const hasOverdue30 = aging && ((aging.overdue_31_60 || 0) > 0);
              const hasOverdue = aging && ((aging.overdue_1_30 || 0) > 0);
              const badgeColor = hasOverdue90 ? "bg-destructive/15 text-destructive border-destructive/30" : hasOverdue30 ? "bg-category-5/15 text-category-5 border-category-5/30" : hasOverdue ? "bg-accent/15 text-accent border-accent/30" : null;
              const badgeLabel = hasOverdue90 ? "60d+ overdue" : hasOverdue30 ? "31\u201360d overdue" : hasOverdue ? "1\u201330d overdue" : null;
              return (
                <div key={entity} className="p-3 bg-muted rounded-lg border border-border/50">
                  <div className="flex items-center gap-2 mb-2">
                    <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-sm font-semibold text-foreground flex-1 truncate">{entity}</span>
                    {badgeColor && <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${badgeColor}`}>{badgeLabel}</span>}
                  </div>
                  <div className="space-y-0.5 text-xs">
                    <div className="flex justify-between"><span className="text-muted-foreground">Revenue</span><span className="font-mono tabular-nums">${(data.total ?? 0).toFixed(2)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">AR Balance</span><span className="font-mono tabular-nums text-accent">${(data.ar_balance ?? 0).toFixed(2)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Txns</span><span className="font-mono tabular-nums">{data.count}</span></div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {arAging?.length > 0 && (
        <Panel>
          <SectionHead title="AR Aging by Entity" />
          <StackedBarChart
            data={arAging.map((r) => ({
              name: r.billing_entity,
              current: r.current_not_due || 0,
              "1-30d": r.overdue_1_30 || 0,
              "31-60d": r.overdue_31_60 || 0,
              "61-90d": r.overdue_61_90 || 0,
              "90d+": r.overdue_90_plus || 0,
            }))}
            categoryKey="name"
            series={[
              { key: "current", label: "Current", color: t.success },
              { key: "1-30d", label: "1\u201330d", color: t.warning },
              { key: "31-60d", label: "31\u201360d", color: t.category5 },
              { key: "61-90d", label: "61\u201390d", color: t.destructive },
              { key: "90d+", label: "90d+", color: t.destructive },
            ]}
            valueFormatter={valueFormatter}
            height={Math.max(200, arAging.length * 40)}
          />
        </Panel>
      )}

      {arAging?.length > 0 && (
        <div>
          <button
            onClick={() => setArAgingOpen(!arAgingOpen)}
            className="flex items-center gap-2 text-sm font-semibold text-foreground hover:text-foreground mb-3"
          >
            {arAgingOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            AR Aging Detail
            <span className="text-xs font-normal text-muted-foreground">({arAging.length} entities)</span>
          </button>
          {arAgingOpen && <ARAgingTable data={arAging} />}
        </div>
      )}
    </div>
  );
};

export const PLStatement = ({ summary }) => {
  if (!summary) return null;
  const revenue = summary.revenue || 0;
  const cogs = summary.cogs || 0;
  const grossProfit = summary.gross_profit || (revenue - cogs);
  const tax = summary.tax_collected || 0;
  const shrinkage = summary.shrinkage || 0;
  const netProfit = grossProfit - tax - shrinkage;
  const marginPct = summary.margin_pct || (revenue > 0 ? ((grossProfit / revenue) * 100).toFixed(1) : 0);

  const Line = ({ label, value, bold, indent, muted }) => (
    <div className={`flex items-center justify-between py-2 ${indent ? "pl-6" : ""}`}>
      <span className={`text-sm ${bold ? "font-semibold text-foreground" : muted ? "text-muted-foreground" : "text-muted-foreground"}`}>{label}</span>
      <span className={`text-sm tabular-nums font-mono ${bold ? "font-bold text-foreground" : muted ? "text-muted-foreground" : "text-foreground"}`}>{valueFormatter(value)}</span>
    </div>
  );

  return (
    <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
      <Line label="REVENUE" value={revenue} bold />
      <Line label="Cost of Goods Sold" value={cogs} indent />
      <div className="border-t border-border my-1" />
      <div className="flex items-center justify-between py-2">
        <span className="text-sm font-semibold text-foreground">GROSS PROFIT</span>
        <div className="flex items-center gap-3">
          <span className="text-sm tabular-nums font-mono font-bold text-foreground">{valueFormatter(grossProfit)}</span>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${parseFloat(marginPct) >= 40 ? "bg-success/10 text-success" : parseFloat(marginPct) < 30 ? "bg-category-5/10 text-category-5" : "bg-info/10 text-info"}`}>
            {marginPct}%
          </span>
        </div>
      </div>
      {tax > 0 && <Line label="Tax Collected" value={tax} indent muted />}
      {shrinkage > 0 && <Line label="Shrinkage" value={shrinkage} indent muted />}
      {(tax > 0 || shrinkage > 0) && (
        <>
          <div className="border-t border-border my-1" />
          <Line label="NET OPERATING PROFIT" value={netProfit} bold />
        </>
      )}
    </div>
  );
};
