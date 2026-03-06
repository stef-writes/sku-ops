import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Stacked horizontal bar chart, e.g. AR aging buckets per entity.
 *
 * @param {object[]} data
 * @param {string} categoryKey
 * @param {{ key: string, label: string, color: string }[]} series
 * @param {(v: number) => string} [valueFormatter]
 * @param {number} [height=300]
 */
export function StackedBarChart({
  data = [],
  categoryKey = "name",
  series: seriesDefs = [],
  valueFormatter = (v) => String(v),
  height = 300,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    const categories = data.map((d) => d[categoryKey] || "—");

    const echartSeries = seriesDefs.map((def, i) => ({
      name: def.label || def.key,
      type: "bar",
      stack: "total",
      barMaxWidth: 20,
      data: data.map((d) => d[def.key] ?? 0),
      itemStyle: {
        color: def.color,
        borderRadius:
          i === 0
            ? [3, 0, 0, 3]
            : i === seriesDefs.length - 1
              ? [0, 3, 3, 0]
              : 0,
      },
      emphasis: {
        focus: "series",
        itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,.1)" },
      },
    }));

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params) => {
          const title = params[0]?.axisValue || "";
          const lines = params
            .filter((p) => p.value > 0)
            .map(
              (p) =>
                `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <b>${valueFormatter(p.value)}</b>`,
            );
          return `<div style="font-size:12px"><b>${title}</b><br/>${lines.join("<br/>")}</div>`;
        },
      },
      legend: {
        bottom: 0,
        textStyle: { fontSize: 11, color: t.mutedForeground },
      },
      grid: { left: 8, right: 24, top: 8, bottom: 36, containLabel: true },
      xAxis: { type: "value", show: false },
      yAxis: {
        type: "category",
        data: categories,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 12,
          color: t.foreground,
          width: 160,
          overflow: "truncate",
        },
      },
      series: echartSeries,
    };
  }, [data, categoryKey, seriesDefs, valueFormatter]);

  if (!data.length) return null;

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      theme="skuops"
      opts={{ renderer: "svg" }}
      notMerge
    />
  );
}
