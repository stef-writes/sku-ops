import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Search, AlertTriangle } from "lucide-react";

export function InventoryFilters({
  search,
  onSearchChange,
  filterDept,
  onFilterDeptChange,
  filterLowStock,
  onFilterLowStockChange,
  departments = [],
}) {
  return (
    <div className="card-elevated p-5 mb-6" data-testid="inventory-filters">
      <div className="flex flex-wrap gap-4">
        <div className="flex-1 min-w-[250px] relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <Input
            type="text"
            placeholder="Search by name, SKU, or barcode..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="input-workshop pl-12 w-full"
            data-testid="inventory-search-input"
          />
        </div>
        <select
          value={filterDept}
          onChange={(e) => onFilterDeptChange(e.target.value)}
          className="input-workshop px-4 min-w-[180px]"
          data-testid="inventory-dept-filter"
        >
          <option value="">All Departments</option>
          {departments.map((dept) => (
            <option key={dept.id} value={dept.id}>
              {dept.name}
            </option>
          ))}
        </select>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => onFilterLowStockChange(!filterLowStock)}
              className={`h-11 px-4 border rounded-lg flex items-center gap-2 transition-all ${
                filterLowStock
                  ? "border-amber-400 bg-amber-50 text-amber-700"
                  : "border-slate-200 hover:border-slate-300"
              }`}
              data-testid="inventory-low-stock-filter"
            >
              <AlertTriangle className="w-5 h-5" />
              Low Stock Only
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Shows items where quantity &le; min stock level
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
