import { useMemo } from "react";
import { TrendingUp, DollarSign } from "lucide-react";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { StatCard } from "@/components/StatCard";
import { useReportSales, useReportPL, useReportTrends } from "@/hooks/useReports";
import { HorizontalBarChart } from "@/components/charts/HorizontalBarChart";
import { DotColumnChart } from "@/components/charts/DotColumnChart";
import { ChartExplainer } from "@/components/charts/ChartExplainer";
import { Panel, SectionHead as SectionHeadBase } from "@/components/Panel";
import { PaymentStrip } from "./ReportHelpers";

const Stat = StatCard;
const SectionHead = ({ title, action }) => <SectionHeadBase title={title} action={action} variant="report" />;

export function OperationsTab({ reportFilters }) {
  const t = themeColors();
  const { data: salesReport } = useReportSales(reportFilters);
  const jobPlParams = useMemo(() => ({ ...reportFilters, group_by: "job" }), [reportFilters]);
  const contractorPlParams = useMemo(() => ({ ...reportFilters, group_by: "contractor" }), [reportFilters]);
  const { data: jobPlData } = useReportPL(jobPlParams);
  const { data: contractorPlData } = useReportPL(contractorPlParams);

  const dotColumnParams = useMemo(() => ({ ...reportFilters, group_by: "day" }), [reportFilters]);
  const { data: dailyTrends } = useReportTrends(dotColumnParams);
  const dotColumnData = useMemo(() => {
    if (!dailyTrends?.series) return [];
    return dailyTrends.series.map((d) => ({ date: d.date, value: d.transaction_count || 0 }));
  }, [dailyTrends]);

  const paymentChartData = salesReport?.by_payment_status
    ? Object.entries(salesReport.by_payment_status).map(([name, value]) => ({ name: name.charAt(0).toUpperCase() + name.slice(1), value: parseFloat(value.toFixed(2)) }))
    : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Total Revenue" value={valueFormatter(salesReport?.total_revenue || 0)} icon={DollarSign} accent="blue" note={`${salesReport?.total_transactions || 0} transactions`} />
        <Stat label="COGS" value={valueFormatter(salesReport?.total_cogs || 0)} icon={DollarSign} accent="orange" />
        <Stat label="Gross Profit" value={valueFormatter(salesReport?.gross_profit || 0)} icon={TrendingUp} accent="emerald" note={`${salesReport?.gross_margin_pct ?? 0}% margin`} />
        <Stat label="Avg Transaction" value={valueFormatter(salesReport?.average_transaction || 0)} accent="violet" note="per order" />
      </div>

      {paymentChartData.length > 0 && (
        <Panel>
          <SectionHead title="Payment Status" />
          <PaymentStrip data={paymentChartData} />
        </Panel>
      )}

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

      {dotColumnData.length > 0 && (
        <Panel>
          <SectionHead title="Daily Operational Activity" action={
            <span className="text-xs text-muted-foreground tabular-nums">{dotColumnData.filter((d) => d.value > 0).length} active days</span>
          } />
          <ChartExplainer title="Activity Pattern" bullets={["Each dot is one day — columns are months", "Darker/brighter dots = more transactions that day", "Look for patterns: consistent activity, quiet periods, or spikes", "Gaps or pale columns may indicate supply issues or seasonal slowdowns"]}>
            <DotColumnChart data={dotColumnData} height={260} />
          </ChartExplainer>
        </Panel>
      )}
    </div>
  );
}
