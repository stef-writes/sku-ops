import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Plus, Printer } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { PageHeader } from "@/components/PageHeader";
import { StockHistoryModal } from "@/components/StockHistoryModal";
import { BarcodeLabelsModal } from "@/components/BarcodeLabelsModal";
import { ProductDetailModal } from "@/components/ProductDetailModal";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useProducts, useDeleteProduct } from "@/hooks/useProducts";
import { useDepartments } from "@/hooks/useDepartments";
import { useVendors } from "@/hooks/useVendors";
import { getErrorMessage } from "@/lib/api-client";
import { PAGE_SIZES } from "@/lib/constants";
import { toast } from "sonner";
import { InventoryFilters } from "./InventoryFilters";
import { InventoryTable } from "./InventoryTable";
import { ProductFormDialog } from "./ProductFormDialog";
import { AdjustStockDialog } from "./AdjustStockDialog";

const PAGE_SIZE = PAGE_SIZES.INVENTORY;

const InventoryPage = () => {
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [filterDept, setFilterDept] = useState("");
  const [filterLowStock, setFilterLowStock] = useState(searchParams.get("low_stock") === "1");
  const [page, setPage] = useState(0);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [detailProduct, setDetailProduct] = useState(null);
  const [stockHistoryProduct, setStockHistoryProduct] = useState(null);
  const [adjustProduct, setAdjustProduct] = useState(null);
  const [labelsModalOpen, setLabelsModalOpen] = useState(false);
  const [labelsProducts, setLabelsProducts] = useState([]);
  const [deleteConfirm, setDeleteConfirm] = useState({ open: false, product: null });

  const deleteMutation = useDeleteProduct();

  useEffect(() => {
    const q = searchParams.get("search");
    if (q != null && q !== search) setSearch(q);
  }, [searchParams]);

  useEffect(() => {
    setPage(0);
  }, [search, filterDept, filterLowStock]);

  const queryParams = {
    ...(search && { search }),
    ...(filterDept && { department_id: filterDept }),
    ...(filterLowStock && { low_stock: "true" }),
    limit: String(PAGE_SIZE),
    offset: String(page * PAGE_SIZE),
  };

  const { data: productsData, isLoading: productsLoading } = useProducts(queryParams);
  const { data: departments = [], isLoading: deptsLoading } = useDepartments();
  const { data: vendors = [] } = useVendors();

  const products = productsData?.items ?? (Array.isArray(productsData) ? productsData : []);
  const totalProducts = productsData?.total ?? products.length;
  const loading = productsLoading || deptsLoading;

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

  return (
    <TooltipProvider delayDuration={300}>
      <div className="p-8" data-testid="inventory-page">
        <PageHeader
          title="Inventory"
          subtitle={`${totalProducts} products`}
          action={
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setLabelsProducts(products);
                  setLabelsModalOpen(true);
                }}
                className="h-12 px-6"
              >
                <Printer className="w-5 h-5 mr-2" />
                Print Labels
              </Button>
              <Button onClick={() => openDialog()} className="btn-primary h-12 px-6" data-testid="add-product-btn">
                <Plus className="w-5 h-5 mr-2" />
                Add Product
              </Button>
            </div>
          }
        />

        <p className="text-sm text-slate-500 mb-4">
          SKUs are auto-assigned (e.g. <span className="font-mono">LUM-00001</span>). Search by name, SKU, or barcode.
        </p>

        <InventoryFilters
          search={search}
          onSearchChange={setSearch}
          filterDept={filterDept}
          onFilterDeptChange={setFilterDept}
          filterLowStock={filterLowStock}
          onFilterLowStockChange={setFilterLowStock}
          departments={departments}
        />

        <InventoryTable
          products={products}
          totalProducts={totalProducts}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          onSelectProduct={setDetailProduct}
        />

        <ProductFormDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          editingProduct={editingProduct}
          departments={departments}
          vendors={vendors}
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
          description={deleteConfirm.product ? `Delete "${deleteConfirm.product.name}"? This cannot be undone.` : ""}
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
