import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Waterfall chart for P&L decomposition.
 * Shows Revenue -> deductions -> Net Profit as ascending/descending bars.
 *
 * @param {{ label: string, value: number, type?: "total"|"increase"|"decrease" }[]} items
 * @param {(v: number) => string} [valueFormatter]
 * @param {number} [height=300]
 */
export function WaterfallChart({
  items = [],
  valueFormatter = (v) =>
    `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
  height = 300,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    if (!items.length) return {};

    const labels = items.map((i) => i.label);
    const transparent = [];
    const positive = [];
    const negative = [];

    let running = 0;
    for (const item of items) {
      if (item.type === "total") {
        transparent.push(0);
        positive.push(item.value >= 0 ? item.value : 0);
        negative.push(item.value < 0 ? Math.abs(item.value) : 0);
        running = item.value;
      } else if (item.type === "decrease" || item.value < 0) {
        const absVal = Math.abs(item.value);
        transparent.push(running - absVal);
        positive.push(0);
        negative.push(absVal);
        running -= absVal;
      } else {
        transparent.push(running);
        positive.push(item.value);
        negative.push(0);
        running += item.value;
      }
    }

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params) => {
          const idx = params[0]?.dataIndex;
          if (idx == null) return "";
          const item = items[idx];
          const prefix = item.type === "decrease" || item.value < 0 ? "−" : "";
          return `<div style="font-size:12px"><b>${item.label}</b><br/>${prefix}${valueFormatter(item.value)}</div>`;
        },
      },
      grid: { left: 12, right: 12, top: 20, bottom: 28, containLabel: true },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11, color: t.mutedForeground, interval: 0 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: t.border } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          fontSize: 11,
          color: t.mutedForeground,
          formatter: (v) => valueFormatter(v),
        },
      },
      series: [
        {
          name: "Bridge",
          type: "bar",
          stack: "waterfall",
          data: transparent,
          itemStyle: { color: "transparent" },
          emphasis: { itemStyle: { color: "transparent" } },
        },
        {
          name: "Positive",
          type: "bar",
          stack: "waterfall",
          data: positive,
          barMaxWidth: 40,
          itemStyle: { color: t.success, borderRadius: [3, 3, 0, 0] },
          label: {
            show: true,
            position: "top",
            fontSize: 11,
            color: t.foreground,
            formatter: (p) => (p.value > 0 ? valueFormatter(p.value) : ""),
          },
          emphasis: {
            itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,.1)" },
          },
        },
        {
          name: "Negative",
          type: "bar",
          stack: "waterfall",
          data: negative,
          barMaxWidth: 40,
          itemStyle: { color: t.destructive, borderRadius: [0, 0, 3, 3] },
          label: {
            show: true,
            position: "bottom",
            fontSize: 11,
            color: t.foreground,
            formatter: (p) => (p.value > 0 ? valueFormatter(p.value) : ""),
          },
          emphasis: {
            itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,.1)" },
          },
        },
      ],
    };
  }, [items, valueFormatter]);

  if (!items.length) return null;

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
