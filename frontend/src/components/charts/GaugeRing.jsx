import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Thin-arc gauge ring for a single KPI value.
 *
 * @param {number} value - current value
 * @param {number} max - scale max
 * @param {string} label - metric name (shown below value)
 * @param {string} [unit=""] - suffix (e.g. "×", "%", " days")
 * @param {{ max: number, color: string }[]} [zones] - color zone breakpoints as fraction of max
 * @param {number} [size=160]
 */
export function GaugeRing({
  value = 0,
  max = 100,
  label = "",
  unit = "",
  zones,
  size = 160,
}) {
  const option = useMemo(() => {
    const t = themeColors();
    const resolvedZones = zones ?? [
      { max: 0.33, color: t.destructive },
      { max: 0.66, color: t.category1 },
      { max: 1, color: t.success },
    ];
    const colorStops = resolvedZones.map((z) => [z.max, z.color]);

    return {
      series: [
        {
          type: "gauge",
          startAngle: 220,
          endAngle: -40,
          min: 0,
          max,
          radius: "90%",
          progress: { show: true, width: 10, roundCap: true },
          pointer: { show: false },
          axisLine: {
            lineStyle: {
              width: 10,
              color: colorStops,
            },
          },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: {
            valueAnimation: true,
            fontSize: 22,
            fontWeight: 700,
            fontFamily: "Inter, system-ui, sans-serif",
            color: t.foreground,
            offsetCenter: [0, "0%"],
            formatter: (v) => {
              const display = Number.isInteger(v) ? v : v.toFixed(1);
              return `${display}${unit}`;
            },
          },
          title: {
            fontSize: 11,
            color: t.mutedForeground,
            offsetCenter: [0, "28%"],
          },
          data: [{ value, name: label }],
        },
      ],
    };
  }, [value, max, label, unit, zones]);

  return (
    <ReactECharts
      option={option}
      style={{ height: size, width: size }}
      theme="skuops"
      opts={{ renderer: "svg" }}
      notMerge
    />
  );
}
