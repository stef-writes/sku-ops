import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Separator } from "./ui/separator";
import {
  Edit2,
  Trash2,
  SlidersHorizontal,
  Printer,
  History,
  Package,
} from "lucide-react";
import { format } from "date-fns";
import { TX_TYPE_LABELS } from "@/lib/constants";
import { useStockHistory } from "@/hooks/useProducts";
import { StockBadge } from "@/components/StatusBadge";

export function ProductDetailModal({
  product,
  open,
  onOpenChange,
  allProducts = [],
  onEdit,
  onAdjust,
  onDelete,
  onPrintLabels,
  onViewHistory,
  onFilterByGroup,
}) {
  const [printQty, setPrintQty] = useState(1);

  const { data: historyData, isLoading: historyLoading } = useStockHistory(
    open ? product?.id : null,
  );
  const recentHistory = (historyData?.history || []).slice(0, 5);

  useEffect(() => {
    if (open && product) setPrintQty(1);
  }, [open, product]);

  const hasBarcode = (product?.barcode || product?.sku)?.toString().trim();

  const handlePrint = () => {
    if (!hasBarcode) return;
    const copies = Array.from(
      { length: Math.max(1, Math.min(99, printQty)) },
      () => product,
    );
    onPrintLabels?.(copies);
  };

  const handleDelete = () => {
    onDelete?.(product);
    onOpenChange(false);
  };

  if (!product) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg rounded-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <Package className="w-5 h-5 text-muted-foreground" />
            <span>{product.name}</span>
            <StockBadge product={product} />
          </DialogTitle>
          <div className="rounded-lg bg-muted border border-border/60 px-3 py-2 mt-2 inline-block">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              SKU (permanent ID)
            </p>
            <p className="font-mono font-semibold text-foreground">
              {product.sku}
            </p>
          </div>
        </DialogHeader>

        <Tabs defaultValue="info" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="info">Info</TabsTrigger>
            <TabsTrigger value="printables">Printables</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>

          <TabsContent
            value="info"
            className="flex-1 overflow-auto mt-4 space-y-4"
          >
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">Department</p>
                <p className="font-medium">{product.department_name || "—"}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Unit</p>
                <p className="font-medium">
                  {product.sell_uom || "each"}
                  {(product.pack_qty || 1) > 1 ? ` ×${product.pack_qty}` : ""}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Price</p>
                <p className="font-mono font-medium">
                  ${product.price?.toFixed(2) ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Cost</p>
                <p className="font-mono text-muted-foreground">
                  ${(product.cost || 0).toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Quantity</p>
                <p className="font-mono font-medium">{product.quantity ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Min Stock</p>
                <p className="font-mono">{product.min_stock ?? 5}</p>
              </div>
              <div className="col-span-2">
                <p className="text-muted-foreground">Scan code (barcode)</p>
                <p className="font-mono text-sm">
                  {product.barcode || product.sku || "—"}
                  {!product.barcode && product.sku && (
                    <span className="text-muted-foreground font-normal ml-1">
                      (uses SKU)
                    </span>
                  )}
                </p>
              </div>
              {product.product_group && (
                <div className="col-span-2">
                  <p className="text-muted-foreground">Product Group</p>
                  <div className="flex items-center gap-2">
                    <button
                      className="font-medium text-accent hover:underline text-left"
                      onClick={() => onFilterByGroup?.(product.product_group)}
                    >
                      {product.product_group}
                    </button>
                    {(() => {
                      const siblings = allProducts.filter(
                        (p) =>
                          p.product_group === product.product_group &&
                          p.id !== product.id,
                      );
                      return siblings.length > 0 ? (
                        <span className="text-xs text-muted-foreground">
                          ({siblings.length} other variant
                          {siblings.length !== 1 ? "s" : ""})
                        </span>
                      ) : null;
                    })()}
                  </div>
                </div>
              )}
              {product.original_sku && (
                <div className="col-span-2">
                  <p className="text-muted-foreground">Vendor / original SKU</p>
                  <p className="font-mono text-sm text-muted-foreground">
                    {product.original_sku}
                  </p>
                </div>
              )}
            </div>
            {product.description && (
              <>
                <Separator />
                <div>
                  <p className="text-muted-foreground text-sm">Description</p>
                  <p className="text-sm">{product.description}</p>
                </div>
              </>
            )}
            <Separator />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onEdit?.(product);
                  onOpenChange(false);
                }}
              >
                <Edit2 className="w-4 h-4 mr-1.5" />
                Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onAdjust?.(product);
                  onOpenChange(false);
                }}
              >
                <SlidersHorizontal className="w-4 h-4 mr-1.5" />
                Adjust Stock
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                onClick={handleDelete}
              >
                <Trash2 className="w-4 h-4 mr-1.5" />
                Delete
              </Button>
            </div>
          </TabsContent>

          <TabsContent
            value="printables"
            className="flex-1 overflow-auto mt-4 space-y-4"
          >
            <p className="text-sm text-muted-foreground">
              Print barcode labels for this product (2×1&quot; format).
            </p>
            {hasBarcode ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <label className="text-sm font-medium">
                    Number of labels
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={99}
                    value={printQty}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      setPrintQty(isNaN(v) ? 1 : Math.min(99, Math.max(1, v)));
                    }}
                    className="w-20"
                  />
                </div>
                <Button onClick={handlePrint}>
                  <Printer className="w-4 h-4 mr-2" />
                  Print {printQty} label{printQty !== 1 ? "s" : ""}
                </Button>
              </div>
            ) : (
              <p className="text-sm text-accent">
                No barcode or SKU set. Edit the product to add a barcode.
              </p>
            )}
          </TabsContent>

          <TabsContent value="history" className="flex-1 overflow-auto mt-4">
            {historyLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : recentHistory.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No transactions yet
              </p>
            ) : (
              <div className="space-y-2">
                {recentHistory.map((tx) => (
                  <div
                    key={tx.id}
                    className="flex items-center justify-between text-sm py-2 border-b border-border/50 last:border-0"
                  >
                    <span className="text-muted-foreground">
                      {TX_TYPE_LABELS[tx.transaction_type] ||
                        tx.transaction_type}
                    </span>
                    <span className="font-mono">
                      {tx.quantity_delta > 0 ? "+" : ""}
                      {tx.quantity_delta}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {tx.created_at
                        ? format(new Date(tx.created_at), "MMM d, HH:mm")
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              className="mt-4 w-full"
              onClick={() => {
                onViewHistory?.(product);
                onOpenChange(false);
              }}
            >
              <History className="w-4 h-4 mr-2" />
              View full history
            </Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
