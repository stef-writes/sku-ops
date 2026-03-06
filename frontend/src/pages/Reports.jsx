import { useState, useMemo } from "react";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  TrendingUp, Package, DollarSign, Calendar as CalendarIcon,
  Download, Receipt, Activity,
} from "lucide-react";
import { format } from "date-fns";
import { DATE_PRESETS } from "@/lib/constants";
import { dateToISO, endOfDayISO } from "@/lib/utils";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { useFinancialSummary } from "@/hooks/useFinancials";
import { useReportArAging } from "@/hooks/useReports";
import { ProductDetailModal } from "@/components/ProductDetailModal";
import { FinanceTab } from "@/components/reports/ReportHelpers";
import { PLTab } from "@/components/reports/PLTab";
import { OperationsTab } from "@/components/reports/OperationsTab";
import { InventoryTab } from "@/components/reports/InventoryTab";
import { TrendsTab } from "@/components/reports/TrendsTab";

const Reports = () => {
  const [activeTab, setActiveTab] = useState("pl");
  const [trendsGroupBy, setTrendsGroupBy] = useState("day");
  const [dateRange, setDateRange] = useState({ from: null, to: null });
  const [arAgingOpen, setArAgingOpen] = useState(true);
  const [selectedProduct, setSelectedProduct] = useState(null);

  const dateParams = useMemo(() => ({
    start_date: dateToISO(dateRange.from),
    end_date: endOfDayISO(dateRange.to),
  }), [dateRange]);

  const reportFilters = useMemo(() => ({ ...dateParams }), [dateParams]);

  const { data: financialSummary } = useFinancialSummary(dateParams);
  const { data: arAging } = useReportArAging(dateParams);

  const handleProductClick = (product) => {
    setSelectedProduct({ id: product.product_id || product.id, name: product.name, sku: product.sku });
  };

  const handleExportCSV = () => {
    const a = document.createElement("a");
    a.download = `report-${activeTab}-${format(new Date(), "yyyy-MM-dd")}.csv`;
    a.click();
  };

  return (
    <div className="p-4 md:p-8" data-testid="reports-page">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">Reports</h1>
          <p className="text-muted-foreground mt-1 text-sm">P&L, operations, inventory, and trend analytics</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-0.5 bg-muted rounded-lg p-0.5">
            {DATE_PRESETS.map((preset) => (
              <button key={preset.label} onClick={() => setDateRange(preset.getValue())} className="text-xs px-3 py-1.5 rounded-md text-muted-foreground hover:bg-card hover:shadow-sm transition-all font-medium">{preset.label}</button>
            ))}
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2" data-testid="date-range-btn">
                <CalendarIcon className="w-4 h-4" />
                {dateRange.from ? dateRange.to ? `${format(dateRange.from, "MMM d")} – ${format(dateRange.to, "MMM d")}` : format(dateRange.from, "MMM d, yyyy") : "Custom"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="end"><Calendar mode="range" selected={dateRange} onSelect={(r) => setDateRange(r || { from: null, to: null })} numberOfMonths={2} /></PopoverContent>
          </Popover>
          {(dateRange.from || dateRange.to) && <button onClick={() => setDateRange({ from: null, to: null })} className="text-xs text-muted-foreground hover:text-foreground">Clear</button>}
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-2" data-testid="export-csv-btn"><Download className="w-4 h-4" />Export</Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-transparent border-b border-border rounded-none p-0 h-auto gap-0 w-full justify-start overflow-x-auto" data-testid="report-tabs">
          {[
            { value: "pl", label: "P&L", icon: Receipt },
            { value: "finance", label: "Finance", icon: DollarSign },
            { value: "operations", label: "Operations", icon: Activity },
            { value: "inventory", label: "Inventory", icon: Package },
            { value: "trends", label: "Trends", icon: TrendingUp },
          ].map(({ value, label, icon: Icon }) => (
            <TabsTrigger key={value} value={value} className="rounded-none border-b-2 border-transparent data-[state=active]:border-accent data-[state=active]:text-foreground text-muted-foreground px-5 py-3 text-sm font-semibold gap-2 bg-transparent shadow-none shrink-0" data-testid={`${value}-tab`}>
              <Icon className="w-4 h-4" />{label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="pl" className="mt-6" data-testid="pl-report-content">
          <PLTab reportFilters={reportFilters} dateParams={dateParams} />
        </TabsContent>

        <TabsContent value="finance" className="mt-6" data-testid="finance-report-content">
          <FinanceTab financialSummary={financialSummary} arAging={arAging} arAgingOpen={arAgingOpen} setArAgingOpen={setArAgingOpen} />
        </TabsContent>

        <TabsContent value="operations" className="mt-6" data-testid="operations-report-content">
          <OperationsTab reportFilters={reportFilters} />
        </TabsContent>

        <TabsContent value="inventory" className="mt-6" data-testid="inventory-report-content">
          <InventoryTab dateParams={dateParams} onProductClick={handleProductClick} />
        </TabsContent>

        <TabsContent value="trends" className="mt-6" data-testid="trends-report-content">
          <TrendsTab reportFilters={reportFilters} dateParams={dateParams} trendsGroupBy={trendsGroupBy} setTrendsGroupBy={setTrendsGroupBy} onProductClick={handleProductClick} />
        </TabsContent>
      </Tabs>

      <ProductDetailModal product={selectedProduct} open={!!selectedProduct} onOpenChange={(open) => !open && setSelectedProduct(null)} />
    </div>
  );
};

export default Reports;
