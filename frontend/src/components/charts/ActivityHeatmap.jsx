import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { themeColors } from "../../lib/chartTheme";

/**
 * Calendar heatmap showing daily activity intensity over trailing months.
 *
 * @param {{ date: string, value: number }[]} data - [{date:"2025-12-01", value:5}, ...]
 * @param {string} [label="transactions"]
 * @param {(v: number) => string} [tooltipExtra] - optional extra tooltip per day
 * @param {number} [height=164]
 */
export function ActivityHeatmap({
  data = [],
  label = "transactions",
  tooltipExtra,
  height = 164,
}) {
  const { option } = useMemo(() => {
    const t = themeColors();
    if (!data.length) return { calendarRange: null, option: {} };

    const dates = data.map((d) => d.date).sort();
    const rangeStart = dates[0];
    const rangeEnd = dates[dates.length - 1];
    const maxVal = Math.max(...data.map((d) => d.value), 1);

    const heatmapData = data.map((d) => [d.date, d.value]);

    return {
      calendarRange: [rangeStart, rangeEnd],
      option: {
        tooltip: {
          formatter: (params) => {
            const [date, value] = params.value || [];
            const extra = tooltipExtra
              ? `<br/>${tooltipExtra(data.find((d) => d.date === date))}`
              : "";
            return `<div style="font-size:12px"><b>${date}</b><br/>${value} ${label}${extra}</div>`;
          },
        },
        visualMap: {
          min: 0,
          max: maxVal,
          show: false,
          inRange: {
            // Empty → low → medium → high → peak (green = activity, intuitive)
            color: ["#1e293b", "#0f766e", "#14b8a6", "#2dd4bf", "#5eead4"],
          },
        },
        calendar: {
          top: 28,
          left: 40,
          right: 12,
          bottom: 4,
          cellSize: [14, 14],
          range: [rangeStart, rangeEnd],
          itemStyle: {
            borderWidth: 2,
            borderColor: t.card,
            borderRadius: 2,
          },
          yearLabel: { show: false },
          monthLabel: {
            fontSize: 11,
            color: t.mutedForeground,
            nameMap: "en",
          },
          dayLabel: {
            firstDay: 1,
            fontSize: 11,
            fontWeight: 500,
            color: t.foreground,
            nameMap: ["", "M", "", "W", "", "F", ""],
          },
          splitLine: { show: false },
        },
        series: [
          {
            type: "heatmap",
            coordinateSystem: "calendar",
            data: heatmapData,
            emphasis: {
              itemStyle: {
                borderColor: t.foreground,
                borderWidth: 1,
              },
            },
          },
        ],
      },
    };
  }, [data, label, tooltipExtra]);

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
