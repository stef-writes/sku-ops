import { useState } from "react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Columns3,
  Search,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

function getOptions(col, data) {
  if (col.filterValues) {
    return col.filterValues.map((v) =>
      typeof v === "object" ? v : { value: v, label: v }
    );
  }
  if (!data?.length) return [];
  const unique = [
    ...new Set(
      data
        .map((row) => {
          const raw = col.filterAccessor
            ? col.filterAccessor(row)
            : row[col.key];
          return raw != null ? String(raw) : null;
        })
        .filter(Boolean)
    ),
  ].sort();
  return unique.map((v) => ({ value: v, label: v }));
}

function PillFilter({ label, value, onChange, options }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 hidden sm:inline">
        {label}
      </span>
      <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
        <button
          onClick={() => onChange(null)}
          className={cn(
            "text-xs px-2.5 py-1 rounded-md font-medium transition-all",
            !value
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          )}
        >
          All
        </button>
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(value === opt.value ? null : opt.value)}
            className={cn(
              "text-xs px-2.5 py-1 rounded-md font-medium transition-all",
              value === opt.value
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function DropdownFilter({ label, value, onChange, options }) {
  return (
    <Select value={value || "__all__"} onValueChange={(v) => onChange(v === "__all__" ? null : v)}>
      <SelectTrigger className="h-7 text-xs w-auto min-w-[100px]">
        <SelectValue placeholder={`All ${label}`} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">All {label}</SelectItem>
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function SortDropdown({ columns, sortBy, sortDir, onSortChange }) {
  if (columns.length === 0) return null;
  return (
    <div className="flex items-center gap-1">
      <Select value={sortBy || "__none__"} onValueChange={(v) => onSortChange(v === "__none__" ? null : v, sortDir)}>
        <SelectTrigger className="h-7 text-xs w-auto min-w-[90px]">
          <SelectValue placeholder="Sort by…" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">Sort by…</SelectItem>
          {columns.map((col) => (
            <SelectItem key={col.key} value={col.key}>{col.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {sortBy && (
        <button
          onClick={() =>
            onSortChange(sortBy, sortDir === "asc" ? "desc" : "asc")
          }
          className="h-7 w-7 flex items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-colors"
          title={sortDir === "asc" ? "Ascending" : "Descending"}
        >
          {sortDir === "asc" ? (
            <ArrowUp className="w-3.5 h-3.5" />
          ) : (
            <ArrowDown className="w-3.5 h-3.5" />
          )}
        </button>
      )}
    </div>
  );
}

function ColumnsPopover({ columns, hiddenColumns, onToggle, onShowAll }) {
  const [open, setOpen] = useState(false);
  const hiddenCount = hiddenColumns.size;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "h-7 w-7 flex items-center justify-center rounded-lg border text-xs transition-colors",
            hiddenCount > 0
              ? "border-amber-200 bg-amber-50 text-amber-700"
              : "border-slate-200 bg-white text-slate-500 hover:text-slate-700 hover:bg-slate-50"
          )}
          title="Show/hide columns"
        >
          <Columns3 className="w-3.5 h-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-48 p-2" align="end">
        <div className="flex items-center justify-between px-1 mb-1">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Columns
          </span>
          {hiddenCount > 0 && (
            <button
              onClick={onShowAll}
              className="text-[10px] text-slate-400 hover:text-slate-600"
            >
              Show all
            </button>
          )}
        </div>
        <div className="space-y-0.5">
          {columns.map((col) => (
            <label
              key={col.key}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-slate-50 cursor-pointer text-sm"
            >
              <Checkbox
                checked={!hiddenColumns.has(col.key)}
                onCheckedChange={() => onToggle(col.key)}
              />
              {col.label}
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Simple view toolbar: search, pill/dropdown filters, sort, column visibility.
 * Designed for warehouse workers, not data analysts.
 */
export function ViewToolbar({
  controller,
  columns,
  data = [],
  resultCount,
  actions,
  className,
}) {
  const {
    search,
    setSearch,
    filters,
    setFilter,
    clearFilters,
    sortBy,
    sortDir,
    setSort,
    hiddenColumns,
    toggleColumn,
    showAllColumns,
    hasActiveFilters,
  } = controller;

  const filterableColumns = columns.filter(
    (c) => c.type === "enum" && c.filterable !== false
  );
  const sortableColumns = columns.filter((c) => c.sortable !== false);

  const totalCount = data.length;
  const showResultCount =
    resultCount != null &&
    hasActiveFilters &&
    resultCount !== totalCount;

  return (
    <div
      className={cn(
        "bg-white border border-slate-200 rounded-xl shadow-sm",
        className
      )}
    >
      <div className="px-4 py-2.5 flex flex-wrap items-center gap-2.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 pl-8 pr-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-200 focus:border-amber-400 w-44"
          />
        </div>

        {filterableColumns.length > 0 && (
          <div className="w-px h-5 bg-slate-200" />
        )}

        {filterableColumns.map((col) => {
          const options = getOptions(col, data);
          const style =
            col.filterStyle ||
            (options.length <= 5 ? "pills" : "dropdown");

          if (style === "pills") {
            return (
              <PillFilter
                key={col.key}
                label={col.label}
                value={filters[col.key] || null}
                onChange={(v) => setFilter(col.key, v)}
                options={options}
              />
            );
          }
          return (
            <DropdownFilter
              key={col.key}
              label={col.label}
              value={filters[col.key] || null}
              onChange={(v) => setFilter(col.key, v)}
              options={options}
            />
          );
        })}

        <div className="flex-1" />

        {showResultCount && (
          <span className="text-xs text-slate-400 tabular-nums">
            {resultCount} of {totalCount}
          </span>
        )}

        <SortDropdown
          columns={sortableColumns}
          sortBy={sortBy}
          sortDir={sortDir}
          onSortChange={setSort}
        />

        <ColumnsPopover
          columns={columns}
          hiddenColumns={hiddenColumns}
          onToggle={toggleColumn}
          onShowAll={showAllColumns}
        />

        {actions}

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="h-7 px-2 flex items-center gap-1 rounded-lg text-xs text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
