import { useState, useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "./EmptyState";

const PAGE_SIZE = 10;

/**
 * DataTable with sorting and pagination.
 * @param {Object} props
 * @param {Array} props.data - Array of row objects
 * @param {Array<{key: string, label: string, sortable?: boolean, render?: (row) => ReactNode}>} props.columns
 * @param {string} [props.emptyMessage] - Message when no data
 * @param {React.ComponentType} [props.emptyIcon] - Icon when no data
 * @param {function(row): ReactNode} [props.rowActions] - Render action buttons for each row
 * @param {number} [props.pageSize] - Rows per page
 * @param {string} [props.className] - Additional classes
 */
export function DataTable({
  data = [],
  columns = [],
  emptyMessage = "No data",
  emptyIcon,
  rowActions,
  pageSize = PAGE_SIZE,
  className,
}) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(1);

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      const cmp = typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va ?? "").localeCompare(String(vb ?? ""));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  const totalPages = Math.ceil(sortedData.length / pageSize) || 1;
  const paginatedData = sortedData.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  };

  const SortIcon = ({ col }) => {
    if (col.sortable === false) return null;
    if (sortKey !== col.key) {
      return <ArrowUpDown className="w-4 h-4 ml-1 opacity-50" />;
    }
    return sortDir === "asc" ? (
      <ArrowUp className="w-4 h-4 ml-1" />
    ) : (
      <ArrowDown className="w-4 h-4 ml-1" />
    );
  };

  if (data.length === 0) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyMessage}
        className={className}
      />
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="rounded-lg border border-slate-200 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50 hover:bg-slate-50">
              {columns.map((col) => (
                <TableHead
                  key={col.key}
                  className={cn(
                    "font-semibold text-slate-700 uppercase text-xs tracking-wider",
                    col.sortable !== false && "cursor-pointer select-none"
                  )}
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                >
                  <span className="flex items-center">
                    {col.label}
                    <SortIcon col={col} />
                  </span>
                </TableHead>
              ))}
              {rowActions && <TableHead className="w-[100px] text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row, idx) => (
              <TableRow key={row.id ?? idx} className="hover:bg-slate-50/50">
                {columns.map((col) => (
                  <TableCell key={col.key} className="py-3">
                    {col.render ? col.render(row) : row[col.key]}
                  </TableCell>
                ))}
                {rowActions && (
                  <TableCell className="text-right py-3">{rowActions(row)}</TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-1">
          <p className="text-sm text-slate-500">
            Page {page} of {totalPages} ({sortedData.length} items)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
