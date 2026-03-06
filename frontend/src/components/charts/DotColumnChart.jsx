import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Dot-column chart: vertical columns of dots per month.
 * Each dot is a day, color intensity = value.
 *
 * @param {{ date: string, value: number }[]} data - daily data [{date:"2025-12-01", value:5}]
 * @param {number} [height=260]
 */
export function DotColumnChart({ data = [], height = 260 }) {
  const option = useMemo(() => {
    const t = themeColors();
    if (!data.length) return {};

    const monthSet = new Set();
    const points = [];
    let maxVal = 0;

    for (const d of data) {
      const dt = new Date(d.date);
      const mKey = `${dt.getFullYear()}-${String(dt.getMonth()).padStart(2, "0")}`;
      monthSet.add(mKey);
      const dayOfMonth = dt.getDate();
      maxVal = Math.max(maxVal, d.value);
      points.push([mKey, dayOfMonth, d.value, d.date]);
    }

    const monthKeys = [...monthSet].sort();
    const monthLabels = monthKeys.map((k) => {
      const [, m] = k.split("-");
      return MONTHS[parseInt(m, 10)];
    });

    const scatterData = points.map(([mKey, day, val, date]) => [
      monthKeys.indexOf(mKey),
      day,
      val,
      date,
    ]);

    return {
      tooltip: {
        formatter: (params) => {
          const [, , val, date] = params.value;
          return `<div style="font-size:12px"><b>${date}</b><br/>${val} transactions</div>`;
        },
      },
      visualMap: {
        min: 0,
        max: maxVal || 1,
        show: false,
        inRange: {
          color: [t.border, "#fcd34d", "#f59e0b", "#d97706"],
        },
      },
      grid: { left: 32, right: 12, top: 8, bottom: 28, containLabel: false },
      xAxis: {
        type: "category",
        data: monthLabels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11, color: t.mutedForeground },
      },
      yAxis: {
        type: "value",
        min: 1,
        max: 31,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      series: [
        {
          type: "scatter",
          data: scatterData,
          symbolSize: 8,
          itemStyle: { borderRadius: 2 },
          emphasis: {
            itemStyle: { borderColor: t.foreground, borderWidth: 1 },
          },
        },
      ],
    };
  }, [data]);

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
