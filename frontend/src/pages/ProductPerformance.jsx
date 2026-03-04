import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "../components/ui/popover";
import {
  TrendingUp,
  Calendar as CalendarIcon,
  Download,
  RotateCcw,
  DollarSign,
  Package,
} from "lucide-react";
import { format } from "date-fns";
import { Card, Metric } from "@tremor/react";
import { DataTable } from "../components/DataTable";

import { API } from "@/lib/api";
import { valueFormatter } from "@/lib/chartConfig";
import { DATE_PRESETS } from "@/lib/constants";

const MarginBadge = ({ pct }) => {
  const cls =
    pct >= 40
      ? "text-emerald-700 bg-emerald-50 border border-emerald-200"
      : pct < 30
      ? "text-orange-700 bg-orange-50 border border-orange-200"
      : "text-slate-700 bg-slate-100 border border-slate-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-bold ${cls}`}>
      {pct}%
    </span>
  );
};

const columns = [
  { key: "name", label: "Product", sortable: true },
  {
    key: "sku",
    label: "SKU",
    sortable: false,
    render: (r) => <span className="font-mono text-xs text-slate-500">{r.sku || "—"}</span>,
  },
  { key: "department", label: "Dept", sortable: true },
  { key: "current_stock", label: "Stock", sortable: true },
  {
    key: "catalog_unit_cost",
    label: "Catalog Cost",
    sortable: true,
    render: (r) => valueFormatter(r.catalog_unit_cost),
  },
  { key: "units_sold", label: "Sold", sortable: true },
  {
    key: "avg_cost_per_unit",
    label: "Avg Cost/Unit",
    sortable: true,
    render: (r) => valueFormatter(r.avg_cost_per_unit),
  },
  {
    key: "revenue",
    label: "Revenue",
    sortable: true,
    render: (r) => valueFormatter(r.revenue),
  },
  {
    key: "cogs",
    label: "COGS",
    sortable: true,
    render: (r) => valueFormatter(r.cogs),
  },
  {
    key: "gross_profit",
    label: "Gross Profit",
    sortable: true,
    render: (r) => valueFormatter(r.gross_profit),
  },
  {
    key: "margin_pct",
    label: "Margin",
    sortable: true,
    render: (r) => <MarginBadge pct={r.margin_pct} />,
  },
  {
    key: "sell_through_pct",
    label: "Sell-Through",
    sortable: true,
    render: (r) => `${r.sell_through_pct}%`,
  },
];

const ProductPerformance = () => {
  const [kpis, setKpis] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState({ from: null, to: null });

  useEffect(() => {
    fetchData();
  }, [dateRange]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateRange.from) params.append("start_date", dateRange.from.toISOString());
      if (dateRange.to) params.append("end_date", dateRange.to.toISOString());

      const [kpisRes, perfRes] = await Promise.all([
        axios.get(`${API}/reports/kpis?${params}`),
        axios.get(`${API}/reports/product-performance?${params}`),
      ]);

      setKpis(kpisRes.data);
      setProducts(perfRes.data.products || []);
    } catch (error) {
      console.error("Error fetching performance data:", error);
      toast.error("Failed to load product performance");
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = () => {
    const rows = [
      ["Product Performance Report"],
      ["Date Range", dateRange.from
        ? (dateRange.to
          ? `${format(dateRange.from, "yyyy-MM-dd")} to ${format(dateRange.to, "yyyy-MM-dd")}`
          : format(dateRange.from, "yyyy-MM-dd"))
        : "All time"],
      [],
      ["KPIs"],
      ["Inventory Turnover", kpis?.inventory_turnover ?? ""],
      ["Days Inventory Outstanding", kpis?.dio ?? ""],
      ["Sell-Through %", kpis?.sell_through_pct ?? ""],
      ["Gross Margin %", kpis?.gross_margin_pct ?? ""],
      ["Total COGS", kpis?.total_cogs ?? ""],
      [],
      ["Name", "SKU", "Department", "Stock", "Catalog Cost", "Units Sold", "Avg Cost/Unit", "Revenue", "COGS", "Gross Profit", "Margin %", "Sell-Through %"],
      ...products.map((p) => [
        p.name, p.sku, p.department, p.current_stock, p.catalog_unit_cost,
        p.units_sold, p.avg_cost_per_unit, p.revenue, p.cogs,
        p.gross_profit, p.margin_pct, p.sell_through_pct,
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `product-performance-${format(new Date(), "yyyy-MM-dd")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-slate-600 font-heading text-xl uppercase tracking-wider">
          Loading Performance Data...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8" data-testid="product-performance-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading font-bold text-3xl text-slate-900 uppercase tracking-wider">
            Product Performance
          </h1>
          <p className="text-slate-600 mt-1">
            Historical COGS, margins, turnover, and sell-through by product
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {DATE_PRESETS.map((preset) => (
              <Button
                key={preset.label}
                variant="outline"
                size="sm"
                onClick={() => setDateRange(preset.getValue())}
              >
                {preset.label}
              </Button>
            ))}
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="btn-secondary h-12 px-4">
                <CalendarIcon className="w-5 h-5 mr-2" />
                {dateRange.from ? (
                  dateRange.to ? (
                    <>{format(dateRange.from, "MMM d")} - {format(dateRange.to, "MMM d")}</>
                  ) : (
                    format(dateRange.from, "MMM d, yyyy")
                  )
                ) : (
                  "All Time"
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={(range) => setDateRange(range || { from: null, to: null })}
                numberOfMonths={2}
              />
            </PopoverContent>
          </Popover>
          {(dateRange.from || dateRange.to) && (
            <Button
              variant="ghost"
              onClick={() => setDateRange({ from: null, to: null })}
              className="h-12"
            >
              Clear
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleExportCSV}>
            <Download className="w-4 h-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <Card className="card-workshop">
          <Metric color="blue">{kpis?.inventory_turnover ?? "—"}×</Metric>
          <p className="text-sm text-slate-500 uppercase tracking-wide mt-1">Inventory Turnover</p>
          <p className="text-xs text-slate-400 mt-0.5">COGS ÷ inventory value</p>
        </Card>
        <Card className="card-workshop">
          <Metric color="violet">{kpis?.dio ?? "—"} days</Metric>
          <p className="text-sm text-slate-500 uppercase tracking-wide mt-1">Days on Hand</p>
          <p className="text-xs text-slate-400 mt-0.5">avg days of stock remaining</p>
        </Card>
        <Card className="card-workshop">
          <Metric color="emerald">{kpis?.sell_through_pct ?? "—"}%</Metric>
          <p className="text-sm text-slate-500 uppercase tracking-wide mt-1">Sell-Through Rate</p>
          <p className="text-xs text-slate-400 mt-0.5">sold ÷ (sold + on hand)</p>
        </Card>
        <Card className="card-workshop">
          <Metric color="emerald">{kpis?.gross_margin_pct ?? "—"}%</Metric>
          <p className="text-sm text-slate-500 uppercase tracking-wide mt-1">Gross Margin</p>
          <p className="text-xs text-slate-400 mt-0.5">historical COGS basis</p>
        </Card>
        <Card className="card-workshop">
          <Metric color="orange">{valueFormatter(kpis?.total_cogs ?? 0)}</Metric>
          <p className="text-sm text-slate-500 uppercase tracking-wide mt-1">Total COGS</p>
          <p className="text-xs text-slate-400 mt-0.5">cost of goods sold</p>
        </Card>
      </div>

      {/* Product Table */}
      <div className="bg-white border border-slate-200 shadow-hard-sm">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="font-heading font-bold text-lg text-slate-900 uppercase tracking-wider">
            Per-Product Breakdown
          </h2>
          <p className="text-sm text-slate-500">{products.length} products with sales activity</p>
        </div>
        <DataTable
          data={products}
          columns={columns}
          emptyMessage="No sales activity in the selected period"
          emptyIcon={Package}
          pageSize={20}
        />
      </div>
    </div>
  );
};

export default ProductPerformance;
