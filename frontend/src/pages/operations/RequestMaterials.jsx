import { useState, useEffect } from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Trash2, ShoppingCart, Send, Barcode } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { QuantityControl } from "@/components/QuantityControl";
import { useProducts } from "@/hooks/useProducts";
import { useDepartments } from "@/hooks/useDepartments";
import { useCreateMaterialRequest } from "@/hooks/useMaterialRequests";
import { useCart } from "@/hooks/useCart";
import { useBarcodeScanner } from "@/hooks/useBarcodeScanner";
import { UnknownBarcodeSheet } from "@/components/UnknownBarcodeSheet";
import { getErrorMessage } from "@/lib/api-client";
import { SubmitRequestModal } from "./_SubmitRequestModal";

const RequestMaterials = () => {
  const { user } = useAuth();

  const { items: cart, addItem: addToCart, updateQuantity, removeItem, clear: clearCart, syncStock, total: subtotal } = useCart();
  const [search, setSearch] = useState("");
  const [selectedDept, setSelectedDept] = useState("all");
  const [submitOpen, setSubmitOpen] = useState(false);
  const [unknownBarcode, setUnknownBarcode] = useState(null);
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");

  const productParams = { search: search || undefined, department_id: selectedDept !== "all" ? selectedDept : undefined };
  const { data: productsData, isLoading: productsLoading } = useProducts(productParams);
  const { data: allProductsData } = useProducts();
  const { data: departmentsData, isLoading: deptsLoading } = useDepartments();
  const createRequest = useCreateMaterialRequest();

  const departments = departmentsData || [];
  const rawProducts = Array.isArray(productsData) ? productsData : (productsData?.items || []);
  const products = rawProducts.filter((p) => (p.sell_quantity ?? p.quantity) > 0);
  const allProducts = Array.isArray(allProductsData) ? allProductsData : (allProductsData?.items || []);

  useEffect(() => { syncStock(allProducts); }, [allProducts, syncStock]);

  const scanner = useBarcodeScanner({
    onSuccess: (product) => {
      if ((product.sell_quantity ?? product.quantity) <= 0) {
        toast.error("Product out of stock");
        return;
      }
      addToCart(product);
      toast.success(`Added: ${product.sku} (+1)`);
    },
    onNotFound: ({ barcode }) => setUnknownBarcode(barcode),
    onInvalidCheckDigit: (barcode) =>
      toast.error(`Invalid barcode — bad check digit (${barcode})`),
  });


  const handleSubmitRequest = async () => {
    try {
      await createRequest.mutateAsync({
        items: cart.map(({ product_id, sku, name, quantity, unit_price, unit }) => ({
          product_id, sku, name, quantity, unit_price, cost: 0, subtotal: quantity * unit_price, unit: unit || "each",
        })),
        job_id: jobId.trim() || null,
        service_address: serviceAddress.trim() || null,
        notes: notes.trim() || null,
      });
      toast.success("Material request submitted!");
      clearCart(); setSubmitOpen(false); setJobId(""); setServiceAddress(""); setNotes("");
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  if (productsLoading && deptsLoading) return <PageSkeleton />;

  return (
    <div className="flex h-screen" data-testid="request-materials-page">
      <div className="w-80 bg-card border-r border-border flex flex-col shadow-sm">
        <div className="p-5 border-b border-border">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-foreground">My Request</h2>
            {cart.length > 0 && <button onClick={clearCart} className="text-xs text-destructive hover:underline">Clear</button>}
          </div>
          {user?.company && <p className="text-xs text-muted-foreground mt-0.5">{user.company}</p>}
        </div>

        <div className="p-3 border-b border-border bg-muted/80">
          <div className="flex-1 relative">
            <Barcode className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <Input
              ref={scanner.inputRef}
              type="text"
              placeholder="Scan barcode…"
              value={scanner.value}
              onChange={(e) => scanner.setValue(e.target.value)}
              onKeyDown={scanner.onKeyDown}
              className="pl-10 h-9 text-sm"
              autoFocus
              disabled={scanner.scanning}
            />
          </div>
        </div>

        <div className="flex-1 overflow-auto p-3">
          {cart.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShoppingCart className="w-10 h-10 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Cart is empty</p>
            </div>
          ) : (
            <div className="space-y-2">
              {cart.map((item) => (
                <div key={item.product_id} className="bg-muted border border-border rounded-lg p-3">
                  <div className="flex justify-between items-start mb-2">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-[10px] text-muted-foreground">{item.sku}</p>
                      <p className="text-sm font-medium text-foreground truncate">{item.name}</p>
                    </div>
                    <button onClick={() => removeItem(item.product_id)} className="text-muted-foreground/60 hover:text-destructive p-1"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                  <div className="flex items-center justify-between">
                    <QuantityControl value={item.quantity} onChange={(v) => updateQuantity(item.product_id, v)} max={item.max_quantity} />
                    <span className="font-semibold text-sm text-foreground tabular-nums">${(item.quantity * item.unit_price).toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-muted/80">
          <div className="flex justify-between text-sm text-muted-foreground mb-3">
            <span>Subtotal</span>
            <span className="font-mono font-semibold tabular-nums">${subtotal.toFixed(2)}</span>
          </div>
          <Button onClick={() => cart.length > 0 ? setSubmitOpen(true) : toast.error("Cart is empty")} disabled={cart.length === 0} className="w-full btn-primary h-11" data-testid="submit-request-btn">
            <Send className="w-4 h-4 mr-2" />Submit Request
          </Button>
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-muted/80">
        <div className="p-5 bg-card border-b border-border">
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input type="text" placeholder="Search by name, SKU, or barcode..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-11 w-full" />
            </div>
            <Select value={selectedDept} onValueChange={setSelectedDept}>
              <SelectTrigger className="w-[200px]"><SelectValue placeholder="All Departments" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Departments</SelectItem>
                {departments.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-5">
          {products.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground"><p className="text-sm">No materials found</p></div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {products.map((product) => (
                <button key={product.id} onClick={() => addToCart(product)} className="bg-card border border-border rounded-lg overflow-hidden text-left hover:border-border hover:shadow-sm transition-all">
                  <div className="aspect-[4/3] bg-muted flex items-center justify-center border-b border-border/50">
                    <span className="font-mono text-xl text-muted-foreground/60 font-bold">{product.department_name?.slice(0, 3).toUpperCase() || "---"}</span>
                  </div>
                  <div className="p-3">
                    <p className="font-mono text-[10px] text-muted-foreground">{product.sku}</p>
                    <p className="text-sm font-medium text-foreground truncate">{product.name}</p>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="font-semibold text-foreground tabular-nums">${(product.sell_price ?? product.price).toFixed(2)}<span className="text-[10px] font-normal text-muted-foreground ml-0.5">/{product.sell_uom || "ea"}</span></span>
                      <span className="text-[10px] text-muted-foreground">{Math.floor(product.sell_quantity ?? product.quantity)} avail</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <SubmitRequestModal
        open={submitOpen}
        onOpenChange={setSubmitOpen}
        jobId={jobId}
        onJobIdChange={setJobId}
        serviceAddress={serviceAddress}
        onServiceAddressChange={setServiceAddress}
        notes={notes}
        onNotesChange={setNotes}
        onSubmit={handleSubmitRequest}
        isPending={createRequest.isPending}
      />

      <UnknownBarcodeSheet
        open={!!unknownBarcode}
        onOpenChange={(open) => { if (!open) setUnknownBarcode(null); }}
        barcode={unknownBarcode}
        products={allProducts}
        onAddProduct={(product) => {
          addToCart(product);
          toast.success(`Added: ${product.sku} (+1)`);
          setUnknownBarcode(null);
        }}
      />
    </div>
  );
};

export default RequestMaterials;
