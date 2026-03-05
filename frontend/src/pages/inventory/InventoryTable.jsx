import { useMemo } from "react";
import { Info, Package } from "lucide-react";
import { DataTable } from "@/components/DataTable";

export function InventoryTable({
  products,
  totalProducts,
  page,
  pageSize,
  onPageChange,
  onSelectProduct,
}) {
  const columns = useMemo(() => [
    {
      key: "sku",
      label: "SKU",
      render: (row) => <span className="font-mono text-sm">{row.sku}</span>,
    },
    {
      key: "name",
      label: "Product Name",
      render: (row) => (
        <div>
          <p className="font-semibold">{row.name}</p>
          {row.original_sku && <p className="text-xs text-slate-400">Orig: {row.original_sku}</p>}
        </div>
      ),
    },
    {
      key: "department_name",
      label: "Department",
    },
    {
      key: "base_unit",
      label: "Unit",
      sortable: false,
      render: (row) => (
        <span className="text-sm text-slate-600">
          {row.base_unit || "each"}
          {row.sell_uom && row.sell_uom !== row.base_unit && (
            <span className="block text-xs text-slate-400">sell: {row.sell_uom}{(row.pack_qty || 1) > 1 ? ` ×${row.pack_qty}` : ""}</span>
          )}
          {row.sell_uom === row.base_unit && (row.pack_qty || 1) > 1 && (
            <span className="block text-xs text-slate-400">×{row.pack_qty}</span>
          )}
        </span>
      ),
    },
    {
      key: "price",
      label: "Price",
      align: "right",
      render: (row) => <span className="font-mono">${row.price.toFixed(2)}</span>,
      exportValue: (row) => row.price.toFixed(2),
    },
    {
      key: "cost",
      label: "Cost",
      align: "right",
      render: (row) => <span className="font-mono text-slate-500">${(row.cost || 0).toFixed(2)}</span>,
      exportValue: (row) => (row.cost || 0).toFixed(2),
    },
    {
      key: "quantity",
      label: "Quantity",
      align: "right",
      render: (row) => <span className="font-mono">{row.quantity}</span>,
    },
    {
      key: "_status",
      label: "Status",
      sortable: false,
      searchable: false,
      render: (row) =>
        row.quantity === 0 ? (
          <span className="badge-error">Out of Stock</span>
        ) : row.quantity <= row.min_stock ? (
          <span className="badge-warning">Low Stock</span>
        ) : (
          <span className="badge-success">In Stock</span>
        ),
      exportValue: (row) =>
        row.quantity === 0 ? "Out of Stock" : row.quantity <= row.min_stock ? "Low Stock" : "In Stock",
    },
  ], []);

  return (
    <DataTable
      data={products}
      columns={columns}
      emptyMessage="No products found"
      emptyIcon={Package}
      onRowClick={onSelectProduct}
      exportable
      exportFilename="inventory.csv"
      serverPagination={{ page, pageSize, total: totalProducts, onPageChange }}
      rowActions={(product) => (
        <button
          onClick={(e) => { e.stopPropagation(); onSelectProduct(product); }}
          className="p-2 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-sm transition-colors"
          title="View details"
          data-testid={`product-detail-${product.sku}`}
        >
          <Info className="w-4 h-4" />
        </button>
      )}
    />
  );
}
