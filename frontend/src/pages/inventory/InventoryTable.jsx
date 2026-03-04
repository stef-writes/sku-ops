import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  Package,
  Info,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

function SortTh({ label, col, sortKey, sortDir, onSort, className = "" }) {
  const active = sortKey === col;
  return (
    <th
      onClick={() => onSort(col)}
      className={`cursor-pointer select-none hover:bg-slate-100 transition-colors ${className}`}
    >
      <span className="flex items-center gap-1">
        {label}
        {active ? (
          sortDir === "asc" ? (
            <ArrowUp className="w-3 h-3 text-amber-500" />
          ) : (
            <ArrowDown className="w-3 h-3 text-amber-500" />
          )
        ) : (
          <ArrowUpDown className="w-3 h-3 opacity-25" />
        )}
      </span>
    </th>
  );
}

export function InventoryTable({
  products,
  totalProducts,
  page,
  pageSize,
  onPageChange,
  onSelectProduct,
}) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedProducts = useMemo(() => {
    if (!sortKey) return products;
    return [...products].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va ?? "").localeCompare(String(vb ?? ""));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [products, sortKey, sortDir]);

  const totalPages = Math.ceil(totalProducts / pageSize);
  const thProps = { sortKey, sortDir, onSort: handleSort };

  return (
    <>
      <div className="card-elevated overflow-hidden rounded-xl" data-testid="inventory-table">
        <table className="w-full table-workshop">
          <thead>
            <tr>
              <SortTh label="SKU" col="sku" {...thProps} />
              <SortTh label="Product Name" col="name" {...thProps} />
              <SortTh label="Department" col="department_name" {...thProps} />
              <th>Unit</th>
              <SortTh label="Price" col="price" {...thProps} />
              <SortTh label="Cost" col="cost" {...thProps} />
              <SortTh label="Quantity" col="quantity" {...thProps} />
              <SortTh label="Status" col="quantity" {...thProps} />
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedProducts.length === 0 ? (
              <tr>
                <td colSpan="9" className="text-center py-12 text-slate-400">
                  <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>No products found</p>
                </td>
              </tr>
            ) : (
              sortedProducts.map((product) => (
                <tr
                  key={product.id}
                  data-testid={`product-row-${product.sku}`}
                  onClick={() => onSelectProduct(product)}
                  className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                >
                  <td className="font-mono text-sm">{product.sku}</td>
                  <td>
                    <div>
                      <p className="font-semibold">{product.name}</p>
                      {product.original_sku && (
                        <p className="text-xs text-slate-400">Orig: {product.original_sku}</p>
                      )}
                    </div>
                  </td>
                  <td>{product.department_name}</td>
                  <td className="text-sm text-slate-600">
                    {product.sell_uom || "each"}
                    {(product.pack_qty || 1) > 1 ? ` ×${product.pack_qty}` : ""}
                  </td>
                  <td className="font-mono">${product.price.toFixed(2)}</td>
                  <td className="font-mono text-slate-500">${(product.cost || 0).toFixed(2)}</td>
                  <td className="font-mono">{product.quantity}</td>
                  <td>
                    {product.quantity === 0 ? (
                      <span className="badge-error">Out of Stock</span>
                    ) : product.quantity <= product.min_stock ? (
                      <span className="badge-warning">Low Stock</span>
                    ) : (
                      <span className="badge-success">In Stock</span>
                    )}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => onSelectProduct(product)}
                      className="p-2 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-sm transition-colors"
                      title="View details"
                      data-testid={`product-detail-${product.sku}`}
                    >
                      <Info className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalProducts > pageSize && (
        <div className="flex items-center justify-between mt-4 px-1">
          <p className="text-sm text-slate-500">
            Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalProducts)} of{" "}
            {totalProducts}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(Math.max(0, page - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <div className="flex items-center gap-1.5 text-sm text-slate-600">
              <span>Page</span>
              <input
                type="number"
                min={1}
                max={totalPages}
                value={page + 1}
                onChange={(e) => {
                  const p = parseInt(e.target.value, 10) - 1;
                  if (!isNaN(p) && p >= 0 && p < totalPages) onPageChange(p);
                }}
                className="w-14 border border-slate-200 rounded px-2 py-1 text-center text-sm focus:outline-none focus:border-amber-400"
              />
              <span>of {totalPages}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(page + 1)}
              disabled={(page + 1) * pageSize >= totalProducts}
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
