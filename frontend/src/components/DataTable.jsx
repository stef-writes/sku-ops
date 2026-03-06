import { useState, useMemo, useCallback } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Download,
  CheckSquare,
  Square,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "./EmptyState";

const DEFAULT_PAGE_SIZE = 15;

function exportCSV(columns, data, filename = "export.csv") {
  const visibleCols = columns.filter((c) => c.key !== "_actions");
  const header = visibleCols.map((c) => `"${c.label}"`).join(",");
  const rows = data.map((row) =>
    visibleCols
      .map((c) => {
        const val = c.exportValue ? c.exportValue(row) : row[c.key];
        return `"${String(val ?? "").replace(/"/g, '""')}"`;
      })
      .join(",")
  );
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Dynamic data table with sorting, pagination, selection, search, and CSV export.
 *
 * Column shape:
 *   { key, label, sortable?, render?, exportValue?, align?, className?, searchable? }
 *
 * @param {Object} props
 * @param {Array} props.data
 * @param {Array} props.columns
 * @param {string} [props.emptyMessage]
 * @param {React.ComponentType} [props.emptyIcon]
 * @param {function(row): ReactNode} [props.rowActions] - Render action buttons per row
 * @param {function(row): void} [props.onRowClick]
 * @param {number} [props.pageSize]
 * @param {string} [props.className]
 *
 * Selection:
 * @param {Set|Array} [props.selectedIds] - Controlled selected row IDs
 * @param {function(Set): void} [props.onSelectionChange]
 * @param {function(row): boolean} [props.isSelectable] - Per-row selectability
 *
 * Header:
 * @param {string} [props.title]
 * @param {ReactNode} [props.headerActions] - Extra buttons beside export
 * @param {boolean} [props.exportable] - Show CSV export button
 * @param {string} [props.exportFilename]
 * @param {boolean} [props.searchable] - Show search input
 *
 * Server-side pagination (optional — bypasses client-side paging):
 * @param {{ page: number, total: number, pageSize: number, onPageChange: (page: number) => void }} [props.serverPagination]
 *
 * @param {boolean} [props.disableSort] - When true, disables column header sorting (use with ViewToolbar)
 */
export function DataTable({
  data = [],
  columns = [],
  emptyMessage = "No data",
  emptyIcon,
  rowActions,
  onRowClick,
  pageSize = DEFAULT_PAGE_SIZE,
  className,
  selectedIds: controlledSelected,
  onSelectionChange,
  isSelectable,
  title,
  headerActions,
  exportable = false,
  exportFilename = "export.csv",
  searchable = false,
  serverPagination,
  disableSort = false,
}) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  const selectable = !!onSelectionChange;
  const selectedSet = useMemo(
    () =>
      controlledSelected instanceof Set
        ? controlledSelected
        : new Set(controlledSelected ?? []),
    [controlledSelected]
  );

  const searchLower = search.toLowerCase().trim();
  const searchableKeys = useMemo(
    () => columns.filter((c) => c.searchable !== false).map((c) => c.key),
    [columns]
  );

  const filteredData = useMemo(() => {
    if (!searchLower) return data;
    return data.filter((row) =>
      searchableKeys.some((key) =>
        String(row[key] ?? "")
          .toLowerCase()
          .includes(searchLower)
      )
    );
  }, [data, searchLower, searchableKeys]);

  const sortedData = useMemo(() => {
    if (disableSort || !sortKey) return filteredData;
    return [...filteredData].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [filteredData, sortKey, sortDir]);

  const isServerPaged = !!serverPagination;
  const effectivePageSize = isServerPaged ? serverPagination.pageSize : pageSize;
  const totalItems = isServerPaged ? serverPagination.total : sortedData.length;
  const totalPages = Math.ceil(totalItems / effectivePageSize) || 1;
  const currentPage = isServerPaged ? serverPagination.page + 1 : Math.min(page, totalPages);
  const paginatedData = isServerPaged
    ? sortedData
    : sortedData.slice((currentPage - 1) * effectivePageSize, currentPage * effectivePageSize);

  const goToPage = (p) => {
    if (isServerPaged) {
      serverPagination.onPageChange(p - 1);
    } else {
      setPage(p);
    }
  };

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  };

  const toggleRow = useCallback(
    (id, e) => {
      e?.stopPropagation();
      const next = new Set(selectedSet);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      onSelectionChange?.(next);
    },
    [selectedSet, onSelectionChange]
  );

  const toggleAll = useCallback(() => {
    const selectableRows = isSelectable
      ? filteredData.filter(isSelectable)
      : filteredData;
    const allSelected =
      selectableRows.length > 0 &&
      selectableRows.every((r) => selectedSet.has(r.id));
    onSelectionChange?.(
      allSelected ? new Set() : new Set(selectableRows.map((r) => r.id))
    );
  }, [filteredData, selectedSet, isSelectable, onSelectionChange]);

  const SortIcon = ({ col }) => {
    if (disableSort || col.sortable === false) return null;
    if (sortKey !== col.key)
      return <ArrowUpDown className="w-3.5 h-3.5 ml-1 opacity-40" />;
    return sortDir === "asc" ? (
      <ArrowUp className="w-3.5 h-3.5 ml-1" />
    ) : (
      <ArrowDown className="w-3.5 h-3.5 ml-1" />
    );
  };

  const showHeader = title || headerActions || exportable || searchable;

  if (data.length === 0 && !showHeader) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyMessage}
        className={className}
      />
    );
  }

  return (
    <div className={cn("space-y-0", className)}>
      <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        {showHeader && (
          <div className="px-5 py-3 border-b border-border/50 flex flex-wrap items-center gap-3 justify-between">
            <div className="flex items-center gap-3">
              {title && (
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
                  {title}
                  {filteredData.length !== data.length
                    ? ` (${filteredData.length}/${data.length})`
                    : ` (${data.length})`}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {searchable && (
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search…"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                    className="h-8 pl-8 pr-3 rounded-lg border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent w-48"
                  />
                </div>
              )}
              {headerActions}
              {exportable && (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 h-8"
                  onClick={() =>
                    exportCSV(columns, sortedData, exportFilename)
                  }
                >
                  <Download className="w-3.5 h-3.5" />
                  CSV
                </Button>
              )}
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/80 hover:bg-muted/80">
                {selectable && (
                  <TableHead className="w-10 px-3">
                    <button
                      type="button"
                      onClick={toggleAll}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {filteredData.length > 0 &&
                      (isSelectable
                        ? filteredData.filter(isSelectable)
                        : filteredData
                      ).every((r) => selectedSet.has(r.id)) ? (
                        <CheckSquare className="w-4 h-4 text-info" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  </TableHead>
                )}
                {columns.map((col) => (
                  <TableHead
                    key={col.key}
                    className={cn(
                      "text-[10px] font-bold uppercase tracking-[0.1em] text-muted-foreground px-3 py-2.5",
                      col.align === "right" && "text-right",
                      col.align === "center" && "text-center",
                      !disableSort && col.sortable !== false &&
                        "cursor-pointer select-none hover:text-foreground",
                      col.className
                    )}
                    onClick={() =>
                      !disableSort && col.sortable !== false && handleSort(col.key)
                    }
                  >
                    <span
                      className={cn(
                        "inline-flex items-center",
                        col.align === "right" && "justify-end w-full"
                      )}
                    >
                      {col.label}
                      <SortIcon col={col} />
                    </span>
                  </TableHead>
                ))}
                {rowActions && (
                  <TableHead className="w-[140px] px-3 py-2.5" />
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedData.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={
                      columns.length +
                      (selectable ? 1 : 0) +
                      (rowActions ? 1 : 0)
                    }
                    className="text-center py-12 text-muted-foreground text-sm"
                  >
                    {searchLower ? "No results match your search" : emptyMessage}
                  </TableCell>
                </TableRow>
              ) : (
                paginatedData.map((row, idx) => {
                  const rowSelectable = isSelectable
                    ? isSelectable(row)
                    : true;
                  const isSelected = selectedSet.has(row.id);
                  return (
                    <TableRow
                      key={row.id ?? idx}
                      className={cn(
                        "hover:bg-muted/60 transition-colors",
                        onRowClick && "cursor-pointer",
                        isSelected && "bg-info/10"
                      )}
                      onClick={() => onRowClick?.(row)}
                    >
                      {selectable && (
                        <TableCell
                          className="px-3 py-2.5"
                          onClick={(e) => toggleRow(row.id, e)}
                        >
                          {rowSelectable ? (
                            isSelected ? (
                              <CheckSquare className="w-4 h-4 text-info" />
                            ) : (
                              <Square className="w-4 h-4 text-muted-foreground/60" />
                            )
                          ) : (
                            <Square className="w-4 h-4 text-border opacity-30" />
                          )}
                        </TableCell>
                      )}
                      {columns.map((col) => (
                        <TableCell
                          key={col.key}
                          className={cn(
                            "px-3 py-2.5",
                            col.align === "right" && "text-right",
                            col.align === "center" && "text-center",
                            col.cellClassName
                          )}
                        >
                          {col.render ? col.render(row) : row[col.key]}
                        </TableCell>
                      ))}
                      {rowActions && (
                        <TableCell className="px-3 py-2.5 text-right">
                          {rowActions(row)}
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border/50">
            <p className="text-xs text-muted-foreground tabular-nums">
              {(currentPage - 1) * effectivePageSize + 1}–
              {Math.min(currentPage * effectivePageSize, totalItems)} of{" "}
              {totalItems}
            </p>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => goToPage(Math.max(1, currentPage - 1))}
                disabled={currentPage <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums min-w-[4rem] text-center">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => goToPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage >= totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
