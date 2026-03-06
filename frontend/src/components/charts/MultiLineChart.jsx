import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Multi-line / area chart for time-series data.
 *
 * @param {object[]} data
 * @param {string} xKey
 * @param {{ key: string, label: string, color: string }[]} series
 * @param {(v: number) => string} [valueFormatter]
 * @param {number}  [height=300]
 * @param {boolean} [area=false]
 * @param {boolean} [stepped=false]  - step interpolation (honest for financial data)
 * @param {boolean} [dotted=false]   - dotted line style with visible symbols
 * @param {function} [onPointClick]  - callback(dataItem) when a point is clicked
 */
export function MultiLineChart({
  data = [],
  xKey = "date",
  series: seriesDefs = [],
  valueFormatter = (v) => String(v),
  height = 300,
  area = false,
  stepped = false,
  dotted = false,
  onPointClick,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    const categories = data.map((d) => d[xKey]);

    const echartSeries = seriesDefs.map((def) => ({
      name: def.label || def.key,
      type: "line",
      smooth: !stepped && !dotted,
      step: stepped ? "end" : false,
      symbol: "circle",
      symbolSize: dotted ? 5 : 4,
      showSymbol: dotted || data.length <= 31,
      data: data.map((d) => d[def.key] ?? 0),
      lineStyle: {
        width: 2,
        type: dotted ? "dotted" : "solid",
      },
      itemStyle: { color: def.color },
      areaStyle: area ? { opacity: 0.08 } : undefined,
      emphasis: {
        focus: "series",
        itemStyle: { borderWidth: 2, borderColor: t.card },
      },
    }));

    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", crossStyle: { color: t.mutedForeground } },
        formatter: (params) => {
          const title = params[0]?.axisValue || "";
          const lines = params.map(
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
      grid: { left: 12, right: 12, top: 12, bottom: 36, containLabel: true },
      xAxis: {
        type: "category",
        data: categories,
        boundaryGap: false,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 11, color: t.mutedForeground },
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
      series: echartSeries,
    };
  }, [data, xKey, seriesDefs, valueFormatter, area, stepped, dotted]);

  if (!data.length) return null;

  const handleEvents = onPointClick
    ? { click: (params) => onPointClick(data[params.dataIndex]) }
    : undefined;

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      theme="skuops"
      opts={{ renderer: "svg" }}
      onEvents={handleEvents}
      notMerge
    />
  );
}
