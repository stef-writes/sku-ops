import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { TrendingUp, Package, DollarSign, Layers } from "lucide-react";
import { valueFormatter } from "@/lib/chartConfig";
import { themeColors } from "@/lib/chartTheme";
import { StatCard } from "@/components/StatCard";
import {
  useReportInventory,
  useReportKpis,
  useReportProductPerformance,
  useReportReorderUrgency,
  useReportProductActivity,
  useReportMargins,
} from "@/hooks/useReports";
import { useProducts } from "@/hooks/useProducts";
import api from "@/lib/api-client";
import { HorizontalBarChart } from "@/components/charts/HorizontalBarChart";
import { GaugeRing } from "@/components/charts/GaugeRing";
import { ProductBubblePlot } from "@/components/charts/ProductBubblePlot";
import { LollipopChart } from "@/components/charts/LollipopChart";
import { ActivityHeatmap } from "@/components/charts/ActivityHeatmap";
import { ChartExplainer, BubbleChartGuide } from "@/components/charts/ChartExplainer";
import { ReportPanel, ReportSectionHead } from "@/components/ReportPanel";
import { LowStockList } from "./ReportHelpers";

const Stat = StatCard;
const SectionHead = ({ title, action }) => <ReportSectionHead title={title} action={action} />;

export function InventoryTab({ dateParams, onProductClick }) {
  const t = themeColors();
  const navigate = useNavigate();
  const { data: inventoryReport } = useReportInventory();
  const { data: kpis } = useReportKpis(dateParams);
  const { data: perfData } = useReportProductPerformance(dateParams);
  const { data: reorderData } = useReportReorderUrgency();
  const { data: marginsReport } = useReportMargins(dateParams);
  const margins = useMemo(() => marginsReport?.products || [], [marginsReport]);
  const { data: productsList } = useProducts();
  const { data: productGroups } = useQuery({
    queryKey: ["productGroups"],
    queryFn: () => api.products.groups(),
  });

  const [heatmapProductId, setHeatmapProductId] = useState(null);
  const activityParams = useMemo(
    () => ({ product_id: heatmapProductId || undefined }),
    [heatmapProductId],
  );
  const { data: productActivityData } = useReportProductActivity(activityParams);

  const productPerf = perfData?.products || [];
  const reorderProducts = useMemo(() => reorderData?.products || [], [reorderData]);

  const lollipopData = useMemo(
    () =>
      reorderProducts.map((p) => ({
        name: p.name,
        value: p.days_until_stockout,
        urgency: p.urgency,
        id: p.product_id,
        ...p,
      })),
    [reorderProducts],
  );

  const productHeatmapData = useMemo(() => {
    if (!productActivityData?.series) return [];
    return productActivityData.series.map((d) => ({
      date: d.day,
      value: d.transaction_count || 0,
      units: d.units_moved || 0,
    }));
  }, [productActivityData]);

  const departmentChartData = inventoryReport?.by_department
    ? Object.entries(inventoryReport.by_department).map(([name, data]) => ({
        name,
        count: data.count,
        value: parseFloat((data.retail_value || data.value || 0).toFixed(2)),
        cost: parseFloat((data.cost_value || data.cost || 0).toFixed(2)),
      }))
    : [];

  const inStock =
    (inventoryReport?.total_products || 0) -
    (inventoryReport?.low_stock_count || 0) -
    (inventoryReport?.out_of_stock_count || 0);
  const totalP = inventoryReport?.total_products || 1;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat
          label="Total Products"
          value={inventoryReport?.total_products || 0}
          icon={Package}
          accent="blue"
        />
        <Stat
          label="Retail Value"
          value={valueFormatter(inventoryReport?.total_retail_value || 0)}
          icon={DollarSign}
          accent="emerald"
        />
        <Stat
          label="Cost Value"
          value={valueFormatter(inventoryReport?.total_cost_value || 0)}
          icon={Layers}
          accent="slate"
        />
        <Stat
          label="Unrealized Margin"
          value={valueFormatter(
            inventoryReport?.unrealized_margin || inventoryReport?.potential_profit || 0,
          )}
          note={inventoryReport?.margin_pct ? `${inventoryReport.margin_pct}%` : ""}
          icon={TrendingUp}
          accent="amber"
        />
      </div>

      {kpis && (
        <ChartExplainer
          title="Health Gauges"
          position="top-left"
          bullets={[
            "Each gauge shows one key inventory health metric",
            "Green zone = healthy, Amber = needs watching, Red = action needed",
            "Turnover: how many times you sell through stock per period",
            "Sell-Through: % of stock that has been sold",
            "Gross Margin: profit % after cost of goods",
          ]}
        >
          <div className="flex flex-wrap items-center justify-center gap-6">
            <div className="flex flex-col items-center">
              <GaugeRing
                value={kpis.inventory_turnover}
                max={Math.max(kpis.inventory_turnover * 1.5, 6)}
                label="Turnover"
                unit="×"
                zones={[
                  { max: 0.2, color: t.destructive },
                  { max: 0.5, color: t.warning },
                  { max: 1, color: t.success },
                ]}
                size={150}
              />
            </div>
            <div className="flex flex-col items-center">
              <GaugeRing
                value={kpis.sell_through_pct}
                max={100}
                label="Sell-Through"
                unit="%"
                zones={[
                  { max: 0.3, color: t.destructive },
                  { max: 0.6, color: t.warning },
                  { max: 1, color: t.success },
                ]}
                size={150}
              />
            </div>
            <div className="flex flex-col items-center">
              <GaugeRing
                value={kpis.gross_margin_pct}
                max={100}
                label="Gross Margin"
                unit="%"
                zones={[
                  { max: 0.3, color: t.destructive },
                  { max: 0.5, color: t.warning },
                  { max: 1, color: t.success },
                ]}
                size={150}
              />
            </div>
          </div>
        </ChartExplainer>
      )}

      {productPerf.length > 0 && (
        <ReportPanel>
          <SectionHead
            title="Product Portfolio — Sell-Through vs Margin"
            action={
              <span className="text-xs text-muted-foreground">
                {productPerf.length} products · click to drill in
              </span>
            }
          />
          <ChartExplainer title="Product Portfolio" wide content={<BubbleChartGuide />}>
            <ProductBubblePlot products={productPerf} onBubbleClick={onProductClick} height={420} />
          </ChartExplainer>
        </ReportPanel>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ReportPanel>
          <SectionHead
            title="Reorder Urgency — Days to Stockout"
            action={
              lollipopData.length > 0 && (
                <span className="text-xs font-bold text-destructive bg-destructive/10 px-2 py-0.5 rounded-full border border-destructive/30">
                  {
                    lollipopData.filter((d) => d.urgency === "critical" || d.urgency === "high")
                      .length
                  }{" "}
                  urgent
                </span>
              )
            }
          />
          {lollipopData.length > 0 ? (
            <ChartExplainer
              title="Reorder Urgency"
              bullets={[
                "Each dot is a product — fewer days = closer to running out",
                "Red = critical (under 3 days), Orange = high (under 7 days)",
                "Amber = medium (under 30 days), Green = healthy stock",
              ]}
            >
              <LollipopChart
                data={lollipopData.slice(0, 20)}
                valueLabel="days"
                onDotClick={onProductClick}
                height={Math.max(200, Math.min(lollipopData.length, 20) * 28)}
              />
            </ChartExplainer>
          ) : (
            <p className="text-sm text-muted-foreground py-8 text-center">
              All stock levels healthy
            </p>
          )}
        </ReportPanel>
        <ReportPanel>
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
          ) : (
            <p className="text-sm text-muted-foreground py-8 text-center">No data</p>
          )}
        </ReportPanel>
      </div>

      {productGroups?.length > 0 && (
        <ReportPanel>
          <SectionHead
            title="Product Groups"
            action={
              <span className="text-xs text-muted-foreground">{productGroups.length} groups</span>
            }
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {productGroups.map((g) => (
              <button
                key={g.product_group}
                className="border border-border rounded-lg p-3 bg-card text-left hover:border-accent/50 hover:bg-accent/5 transition-colors cursor-pointer"
                onClick={() => navigate(`/inventory?group=${encodeURIComponent(g.product_group)}`)}
              >
                <p className="font-medium text-sm truncate">{g.product_group}</p>
                <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                  <span>
                    {g.product_count} variant{g.product_count !== 1 ? "s" : ""}
                  </span>
                  <span>
                    Total qty:{" "}
                    <strong className="tabular-nums">{Math.round(g.total_quantity)}</strong>
                  </span>
                </div>
              </button>
            ))}
          </div>
        </ReportPanel>
      )}

      <ReportPanel>
        <SectionHead title="Top Products by Revenue" />
        {margins.length > 0 ? (
          <HorizontalBarChart
            data={margins.slice(0, 10).map((p) => ({
              name: p.name || p.product_id,
              revenue: p.revenue,
            }))}
            categoryKey="name"
            series={[{ key: "revenue", label: "Revenue", color: t.category1 }]}
            valueFormatter={valueFormatter}
            height={Math.max(200, Math.min(margins.length, 10) * 36)}
          />
        ) : (
          <p className="text-sm text-muted-foreground py-8 text-center">No data</p>
        )}
      </ReportPanel>

      <ReportPanel>
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
                <option key={p.id} value={p.id}>
                  {p.name} ({p.sku})
                </option>
              ))}
            </select>
          }
        />
        {productHeatmapData.length > 0 ? (
          <ChartExplainer
            title="Activity Heatmap"
            bullets={[
              "Each square is one day — brighter = more withdrawals",
              "Use the dropdown to filter by product",
              "Hover for exact counts",
              "Consistent color = steady demand",
            ]}
          >
            <ActivityHeatmap
              data={productHeatmapData}
              label="withdrawals"
              tooltipExtra={(d) => (d?.units ? `Units moved: ${d.units}` : "")}
            />
          </ChartExplainer>
        ) : (
          <p className="text-sm text-muted-foreground py-6 text-center">
            No withdrawal activity found
          </p>
        )}
      </ReportPanel>

      <ReportPanel>
        <SectionHead title="Stock Health" />
        <div className="flex h-5 rounded-lg overflow-hidden gap-px mb-3">
          <div className="bg-success" style={{ width: `${(inStock / totalP) * 100}%` }} />
          <div
            className="bg-category-5"
            style={{
              width: `${((inventoryReport?.low_stock_count || 0) / totalP) * 100}%`,
            }}
          />
          <div
            className="bg-destructive"
            style={{
              width: `${((inventoryReport?.out_of_stock_count || 0) / totalP) * 100}%`,
            }}
          />
        </div>
        <div className="flex gap-5 text-xs">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full bg-success inline-block" />
            In stock <strong className="tabular-nums">{inStock}</strong>
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full bg-category-5 inline-block" />
            Low <strong className="tabular-nums">{inventoryReport?.low_stock_count || 0}</strong>
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full bg-destructive inline-block" />
            Out <strong className="tabular-nums">{inventoryReport?.out_of_stock_count || 0}</strong>
          </span>
        </div>
      </ReportPanel>

      {inventoryReport?.low_stock_items?.length > 0 && (
        <ReportPanel>
          <SectionHead
            title="Low Stock Alert"
            action={
              <span className="text-xs font-bold text-category-5 bg-category-5/10 px-2 py-0.5 rounded-full border border-category-5/30">
                {inventoryReport.low_stock_count} items
              </span>
            }
          />
          <div className="max-h-[360px] overflow-auto -mx-6 px-6">
            <LowStockList items={inventoryReport.low_stock_items} />
          </div>
        </ReportPanel>
      )}
    </div>
  );
}
