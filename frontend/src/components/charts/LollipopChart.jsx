import { useMemo, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import * as echarts from "echarts/core";
import { themeColors } from "../../lib/chartTheme";

/* URGENCY_COLORS moved inside useMemo — depends on runtime theme */

/**
 * Lollipop chart: thin line + dot for ranked single-value data.
 * Designed for days-until-stockout ranking with urgency coloring.
 *
 * @param {{ name: string, value: number, urgency?: string, id?: string }[]} data
 * @param {string} [valueLabel="days"]
 * @param {function} [onDotClick] - callback(dataItem) when a dot is clicked
 * @param {number} [height=320]
 */
export function LollipopChart({
  data = [],
  valueLabel = "days",
  onDotClick,
  height = 320,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    if (!data.length) return {};

    const URGENCY_COLORS = {
      critical: t.destructive,
      high: t.category5,
      medium: t.category1,
      low: t.success,
      no_data: t.muted,
    };

    const sorted = [...data].sort((a, b) => (a.value ?? Infinity) - (b.value ?? Infinity));
    const categories = sorted.map((d) => {
      const raw = d.name || "—";
      return raw.length > 22 ? raw.slice(0, 20) + "…" : raw;
    });

    echarts.registerCustomSeries ||
      (() => {
        /* noop */
      })();

    return {
      tooltip: {
        formatter: (params) => {
          const item = sorted[params.dataIndex];
          if (!item) return "";
          const val =
            item.value == null ? "Unknown" : `${item.value.toFixed(0)} ${valueLabel}`;
          return `<div style="font-size:12px"><b>${item.name}</b><br/>${val}<br/><span style="color:${URGENCY_COLORS[item.urgency] || URGENCY_COLORS.no_data}">${item.urgency || "no data"}</span></div>`;
        },
      },
      grid: { left: 8, right: 60, top: 8, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: t.border } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 11,
          color: t.mutedForeground,
          formatter: (v) => `${v}d`,
        },
      },
      yAxis: {
        type: "category",
        data: categories,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11, color: t.foreground, width: 140, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: sorted.map((d) => ({
            value: d.value ?? 0,
            itemStyle: {
              color: URGENCY_COLORS[d.urgency] || URGENCY_COLORS.no_data,
              borderRadius: [0, 3, 3, 0],
              opacity: 0.25,
            },
          })),
          barWidth: 3,
          z: 1,
        },
        {
          type: "scatter",
          data: sorted.map((d) => ({
            value: d.value ?? 0,
            itemStyle: {
              color: URGENCY_COLORS[d.urgency] || URGENCY_COLORS.no_data,
            },
          })),
          symbolSize: 10,
          z: 2,
          label: {
            show: true,
            position: "right",
            fontSize: 11,
            color: t.foreground,
            formatter: (p) =>
              p.value != null ? `${Math.round(p.value)}d` : "?",
          },
          emphasis: {
            itemStyle: {
              borderColor: t.foreground,
              borderWidth: 2,
              shadowBlur: 6,
              shadowColor: "rgba(0,0,0,.15)",
            },
          },
        },
      ],
    };
  }, [data, valueLabel]);

  const handleEvents = useCallback(() => {
    if (!onDotClick) return undefined;
    const sorted = [...data].sort(
      (a, b) => (a.value ?? Infinity) - (b.value ?? Infinity),
    );
    return {
      click: (params) => {
        const item = sorted[params.dataIndex];
        if (item) onDotClick(item);
      },
    };
  }, [data, onDotClick]);

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
