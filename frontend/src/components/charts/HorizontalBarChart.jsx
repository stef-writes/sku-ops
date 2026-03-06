import { useMemo, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Reusable horizontal bar chart for ranked lists.
 *
 * @param {object[]} data
 * @param {string}  categoryKey
 * @param {{ key: string, label: string, color: string }[]} series
 * @param {(v: number) => string} [valueFormatter]
 * @param {number}  [height=320]
 * @param {boolean} [showLegend=false]
 * @param {function} [onBarClick] - callback(dataItem) when a bar is clicked
 */
export function HorizontalBarChart({
  data = [],
  categoryKey = "name",
  series: seriesDefs = [],
  valueFormatter = (v) => String(v),
  height = 320,
  showLegend = false,
  onBarClick,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    const sliced = [...data].reverse();
    const categories = sliced.map((d) => {
      const raw = d[categoryKey] || "—";
      return raw.length > 24 ? raw.slice(0, 22) + "…" : raw;
    });

    const echartSeries = seriesDefs.map((def) => ({
      name: def.label || def.key,
      type: "bar",
      data: sliced.map((d) => d[def.key] ?? 0),
      barMaxWidth: 18,
      itemStyle: { color: def.color, borderRadius: [0, 3, 3, 0] },
      label: {
        show: true,
        position: "right",
        fontSize: 11,
        color: t.foreground,
        formatter: (params) => valueFormatter(params.value),
      },
      emphasis: {
        itemStyle: { opacity: 1, shadowBlur: 6, shadowColor: "rgba(0,0,0,.1)" },
        label: { fontWeight: "bold" },
      },
    }));

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params) => {
          const title = params[0]?.axisValue || "";
          const lines = params.map(
            (p) =>
              `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <b>${valueFormatter(p.value)}</b>`,
          );
          return `<div style="font-size:12px"><b>${title}</b><br/>${lines.join("<br/>")}</div>`;
        },
      },
      legend: showLegend
        ? { bottom: 0, textStyle: { fontSize: 11, color: t.mutedForeground } }
        : undefined,
      grid: {
        left: 8,
        right: 80,
        top: 8,
        bottom: showLegend ? 32 : 8,
        containLabel: true,
      },
      xAxis: { type: "value", show: false },
      yAxis: {
        type: "category",
        data: categories,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 12, color: t.foreground, width: 140, overflow: "truncate" },
      },
      series: echartSeries,
    };
  }, [data, categoryKey, seriesDefs, valueFormatter, showLegend]);

  const handleEvents = useCallback(() => {
    if (!onBarClick) return undefined;
    const reversed = [...data].reverse();
    return {
      click: (params) => {
        const item = reversed[params.dataIndex];
        if (item) onBarClick(item);
      },
    };
  }, [data, onBarClick]);

  if (!data.length) return null;

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      theme="skuops"
      opts={{ renderer: "svg" }}
      onEvents={handleEvents()}
      notMerge
    />
  );
}
