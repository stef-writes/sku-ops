import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Plus, Printer, Package } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { QueryError } from "@/components/QueryError";
import { PageHeader } from "@/components/PageHeader";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { BarcodeLabelsModal } from "@/components/BarcodeLabelsModal";
import { ProductDetailModal } from "@/components/ProductDetailModal";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { ViewToolbar } from "@/components/ViewToolbar";
import { useProducts, useDeleteProduct } from "@/hooks/useProducts";
import { useDepartments } from "@/hooks/useDepartments";
import { useViewController } from "@/hooks/useViewController";
import { getErrorMessage } from "@/lib/api-client";
import { toast } from "sonner";
import { ProductFormDialog } from "./ProductFormDialog";
import { AdjustStockDialog } from "./AdjustStockDialog";
import { Info } from "lucide-react";

const InventoryPage = () => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [detailProduct, setDetailProduct] = useState(null);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);
  const [adjustProduct, setAdjustProduct] = useState(null);
  const [labelsModalOpen, setLabelsModalOpen] = useState(false);
  const [labelsProducts, setLabelsProducts] = useState([]);
  const [deleteConfirm, setDeleteConfirm] = useState({
    open: false,
    product: null,
  });
  const [selectedIds, setSelectedIds] = useState(new Set());

  const deleteMutation = useDeleteProduct();

  const {
    data: productsData,
    isLoading: productsLoading,
    isError: productsError,
    error: productsErr,
    refetch: refetchProducts,
  } = useProducts({ limit: 500 });
  const { data: departments = [], isLoading: deptsLoading } = useDepartments();

  const allProducts = useMemo(
    () => productsData?.items ?? (Array.isArray(productsData) ? productsData : []),
    [productsData],
  );
  const loading = productsLoading || deptsLoading;

  const columns = useMemo(
    () => [
      {
        key: "sku",
        label: "SKU",
        type: "text",
        render: (row) => <span className="font-mono text-sm">{row.sku}</span>,
      },
      {
        key: "name",
        label: "Product Name",
        type: "text",
        render: (row) => <p className="font-semibold">{row.name}</p>,
      },
      {
        key: "category_name",
        label: "Category",
        type: "enum",
        filterValues: departments.map((d) => d.name),
      },
      {
        key: "base_unit",
        label: "Unit",
        sortable: false,
        filterable: false,
        render: (row) => (
          <span className="text-sm text-muted-foreground">
            {row.base_unit || "each"}
            {row.sell_uom && row.sell_uom !== row.base_unit && (
              <span className="block text-xs text-muted-foreground">
                sell: {row.sell_uom}
                {(row.pack_qty || 1) > 1 ? ` ×${row.pack_qty}` : ""}
              </span>
            )}
            {row.sell_uom === row.base_unit && (row.pack_qty || 1) > 1 && (
              <span className="block text-xs text-muted-foreground">×{row.pack_qty}</span>
            )}
          </span>
        ),
      },
      {
        key: "price",
        label: "Price",
        type: "number",
        align: "right",
        render: (row) => <span className="font-mono">${row.price.toFixed(2)}</span>,
        exportValue: (row) => row.price.toFixed(2),
      },
      {
        key: "cost",
        label: "Cost",
        type: "number",
        align: "right",
        render: (row) => (
          <span className="font-mono text-muted-foreground">${(row.cost || 0).toFixed(2)}</span>
        ),
        exportValue: (row) => (row.cost || 0).toFixed(2),
      },
      {
        key: "quantity",
        label: "Quantity",
        type: "number",
        align: "right",
        render: (row) => <span className="font-mono">{row.quantity}</span>,
      },
      {
        key: "_status",
        label: "Status",
        type: "enum",
        filterValues: ["In Stock", "Low Stock", "Out of Stock"],
        filterAccessor: (row) =>
          row.quantity === 0
            ? "Out of Stock"
            : row.quantity <= row.min_stock
              ? "Low Stock"
              : "In Stock",
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
          row.quantity === 0
            ? "Out of Stock"
            : row.quantity <= row.min_stock
              ? "Low Stock"
              : "In Stock",
      },
    ],
    [departments],
  );

  const view = useViewController({ columns });
  const processedProducts = view.apply(allProducts);

  const openDialog = (product = null) => {
    setEditingProduct(product);
    setDialogOpen(true);
  };

  const handleDeleteClick = (product) => {
    setDetailProduct(null);
    setDeleteConfirm({ open: true, product });
  };

  const handleDeleteConfirm = async () => {
    const { product } = deleteConfirm;
    if (!product) return;
    try {
      await deleteMutation.mutateAsync(product.id);
      toast.success("Product deleted");
    } catch (error) {
      toast.error(getErrorMessage(error));
      throw error;
    }
  };

  if (loading) {
    return <PageSkeleton />;
  }
  if (productsError) {
    return <QueryError error={productsErr} onRetry={refetchProducts} />;
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="p-8" data-testid="inventory-page">
        <PageHeader
          title="Products"
          subtitle={`${allProducts.length} products`}
          action={
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setLabelsProducts(processedProducts);
                  setLabelsModalOpen(true);
                }}
                className="h-12 px-6"
              >
                <Printer className="w-5 h-5 mr-2" />
                Print Labels
              </Button>
              <Button
                onClick={() => openDialog()}
                className="btn-primary h-12 px-6"
                data-testid="add-product-btn"
              >
                <Plus className="w-5 h-5 mr-2" />
                Add Product
              </Button>
            </div>
          }
        />

        <ViewToolbar
          controller={view}
          columns={columns}
          data={allProducts}
          resultCount={processedProducts.length}
          className="mb-3"
        />

        {selectedIds.size > 0 && (
          <div className="mb-3 flex items-center gap-3 rounded-lg border border-border bg-muted px-4 py-2.5">
            <span className="text-sm font-medium">{selectedIds.size} selected</span>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground ml-auto"
              onClick={() => setSelectedIds(new Set())}
            >
              Deselect
            </Button>
          </div>
        )}

        <DataTable
          data={processedProducts}
          columns={view.visibleColumns}
          emptyMessage="No products found"
          emptyIcon={Package}
          onRowClick={setDetailProduct}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          exportable
          exportFilename="inventory.csv"
          disableSort
          rowActions={(product) => (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setDetailProduct(product);
              }}
              className="p-2 text-muted-foreground hover:text-info hover:bg-info/10 rounded-sm transition-colors"
              title="View details"
              data-testid={`product-detail-${product.sku}`}
            >
              <Info className="w-4 h-4" />
            </button>
          )}
        />

        <ProductFormDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          editingProduct={editingProduct}
          departments={departments}
        />

        <AdjustStockDialog
          product={adjustProduct}
          open={!!adjustProduct}
          onOpenChange={(open) => !open && setAdjustProduct(null)}
        />

        <ProductDetailModal
          product={detailProduct}
          open={!!detailProduct}
          onOpenChange={(open) => !open && setDetailProduct(null)}
          onEdit={(p) => {
            setDetailProduct(null);
            openDialog(p);
          }}
          onAdjust={(p) => {
            setDetailProduct(null);
            setAdjustProduct(p);
          }}
          onDelete={handleDeleteClick}
          onPrintLabels={(prods) => {
            setLabelsProducts(prods);
            setLabelsModalOpen(true);
          }}
          onViewHistory={(p) => {
            setDetailProduct(null);
            setStockHistoryProduct(p);
          }}
        />

        <BarcodeLabelsModal
          products={labelsProducts}
          open={labelsModalOpen}
          onOpenChange={setLabelsModalOpen}
        />

        <StockHistoryModal
          product={stockHistoryProduct}
          open={!!stockHistoryProduct}
          onOpenChange={(open) => !open && setStockHistoryProduct(null)}
        />

        <ConfirmDialog
          open={deleteConfirm.open}
          onOpenChange={(open) => setDeleteConfirm((p) => ({ ...p, open }))}
          title="Delete product"
          description={
            deleteConfirm.product
              ? `Delete "${deleteConfirm.product.name}"? This cannot be undone.`
              : ""
          }
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={handleDeleteConfirm}
          variant="danger"
        />
      </div>
    </TooltipProvider>
  );
};

export default InventoryPage;
