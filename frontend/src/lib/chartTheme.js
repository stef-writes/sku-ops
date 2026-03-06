import * as echarts from "echarts/core";

function hslToHex(hslStr) {
  const [h, sRaw, lRaw] = hslStr.trim().split(/\s+/).map(parseFloat);
  const s = sRaw / 100;
  const l = lRaw / 100;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {
    const k = (n + h / 30) % 12;
    const c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * c).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function resolveThemeColors() {
  return {
    foreground: hslToHex(getCSSVar("--foreground")),
    mutedForeground: hslToHex(getCSSVar("--muted-foreground")),
    muted: hslToHex(getCSSVar("--muted")),
    border: hslToHex(getCSSVar("--border")),
    card: hslToHex(getCSSVar("--card")),
    sidebar: hslToHex(getCSSVar("--sidebar")),
    sidebarForeground: hslToHex(getCSSVar("--sidebar-foreground")),
    accent: hslToHex(getCSSVar("--accent")),
    success: hslToHex(getCSSVar("--success")),
    warning: hslToHex(getCSSVar("--warning")),
    destructive: hslToHex(getCSSVar("--destructive")),
    info: hslToHex(getCSSVar("--info")),
    category1: hslToHex(getCSSVar("--category-1")),
    category2: hslToHex(getCSSVar("--category-2")),
    category3: hslToHex(getCSSVar("--category-3")),
    category4: hslToHex(getCSSVar("--category-4")),
    category5: hslToHex(getCSSVar("--category-5")),
    category6: hslToHex(getCSSVar("--category-6")),
    category7: hslToHex(getCSSVar("--category-7")),
    category8: hslToHex(getCSSVar("--category-8")),
  };
}

let _resolved = null;
export function themeColors() {
  if (!_resolved) _resolved = resolveThemeColors();
  return _resolved;
}

const PALETTE = [
  "#f59e0b",
  "#10b981",
  "#3b82f6",
  "#fb923c",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#84cc16",
];

const FALLBACK_COLORS = {
  foreground: "#e5e7eb",
  mutedForeground: "#94a3b8",
  muted: "#1e293b",
  border: "#334155",
  card: "#111827",
  sidebar: "#0b1220",
  sidebarForeground: "#e2e8f0",
};

export function themePalette() {
  try {
    const t = themeColors();
    return [
      t.category1, t.category2, t.category3, t.category5,
      t.category4, t.category6, t.category7, t.category8,
    ];
  } catch {
    return PALETTE;
  }
}

const resolved = (() => {
  try {
    return themeColors();
  } catch {
    return FALLBACK_COLORS;
  }
})();

echarts.registerTheme("skuops", {
  color: themePalette(),
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
  title: {
    textStyle: { fontSize: 14, fontWeight: 600, color: resolved.foreground },
    subtextStyle: { fontSize: 11, color: resolved.mutedForeground },
  },
  legend: {
    bottom: 0,
    icon: "circle",
    itemWidth: 8,
    itemHeight: 8,
    itemGap: 16,
    textStyle: { fontSize: 11, color: resolved.mutedForeground },
  },
  tooltip: {
    backgroundColor: resolved.sidebar,
    borderColor: resolved.border,
    borderWidth: 1,
    textStyle: { fontSize: 12, color: resolved.sidebarForeground },
    extraCssText:
      "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.3);padding:10px 14px;",
  },
  grid: {
    left: 12,
    right: 12,
    top: 12,
    bottom: 36,
    containLabel: true,
  },
  categoryAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { fontSize: 11, color: resolved.mutedForeground },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { fontSize: 11, color: resolved.mutedForeground },
    splitLine: { lineStyle: { color: resolved.border } },
  },
  line: {
    smooth: false,
    symbolSize: 4,
    lineStyle: { width: 2 },
  },
  bar: {
    barMaxWidth: 20,
    itemStyle: { borderRadius: [0, 3, 3, 0] },
  },
});

export { PALETTE };
