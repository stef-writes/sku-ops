import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Trash2, Check, HardHat, Clock, Loader2, ScanLine, Plus } from "lucide-react";
import { JobPicker } from "@/components/JobPicker";
import { AddressPicker } from "@/components/AddressPicker";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { QuantityControl } from "@/components/QuantityControl";
import { useProducts } from "@/hooks/useProducts";
import { useContractors } from "@/hooks/useContractors";
import { useCreateWithdrawal, useCreateWithdrawalForContractor } from "@/hooks/useWithdrawals";
import { useCart } from "@/hooks/useCart";
import { useBarcodeScanner } from "@/hooks/useBarcodeScanner";
import { UnknownBarcodeSheet } from "@/components/UnknownBarcodeSheet";
import { getErrorMessage } from "@/lib/api-client";

const IssueMaterials = () => {
  const { user } = useAuth();
  const searchRef = useRef(null);
  const dropdownRef = useRef(null);

  const isContractor = user?.role === "contractor";
  const { data: productsData, isLoading: productsLoading } = useProducts();
  const { data: contractorsData, isLoading: contractorsLoading } = useContractors();
  const createWithdrawal = useCreateWithdrawal();
  const createForContractor = useCreateWithdrawalForContractor();

  const allProducts = Array.isArray(productsData) ? productsData : (productsData?.items || []);
  const contractors = (contractorsData || []).filter((c) => c.is_active !== false);

  const { items, addItem, updateQuantity, removeItem, clear: clearCart, syncStock, total: displaySubtotal } = useCart({
    getPrice: (p) => p.sell_price ?? p.price ?? 0,
  });

  useEffect(() => { syncStock(allProducts); }, [allProducts, syncStock]);
  const [search, setSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedContractor, setSelectedContractor] = useState("");
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [unknownBarcode, setUnknownBarcode] = useState(null);

  const scanner = useBarcodeScanner({
    onSuccess: (product) => {
      if ((product.sell_quantity ?? product.quantity) <= 0) {
        toast.error("Product out of stock");
        return;
      }
      addItem(product);
      toast.success(`Added: ${product.sku} (+1)`);
      setSearch("");
      setShowDropdown(false);
    },
    onNotFound: ({ barcode }) => {
      setUnknownBarcode(barcode);
      setSearch("");
      setShowDropdown(false);
    },
    onInvalidCheckDigit: (barcode) =>
      toast.error(`Invalid barcode — bad check digit (${barcode})`),
  });

  useEffect(() => {
    if (isContractor) setSelectedContractor(user.id);
  }, [isContractor, user?.id]);

  useEffect(() => {
    const handler = (e) => {
      if (!searchRef.current?.contains(e.target) && !dropdownRef.current?.contains(e.target)) setShowDropdown(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const searchResults = search.trim().length > 0
    ? allProducts.filter((p) => (p.sell_quantity ?? p.quantity) > 0).filter((p) => {
        const q = search.toLowerCase();
        return p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q);
      }).slice(0, 8)
    : [];

  const handleAddItem = (product) => {
    addItem(product);
    setSearch("");
    setShowDropdown(false);
    searchRef.current?.focus();
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "Enter") {
      // If input looks like a barcode (no spaces, reasonable length), use the
      // scanner path so we get structured error handling and the not-found sheet.
      const val = e.target.value.trim();
      const looksLikeBarcode = val.length > 0 && !val.includes(" ");
      if (looksLikeBarcode && searchResults.length === 0) {
        scanner.onKeyDown(e);
        return;
      }
      if (searchResults.length > 0) {
        const exact = searchResults.find((p) => p.sku.toLowerCase() === val.toLowerCase());
        handleAddItem(exact || searchResults[0]);
      }
    }
    if (e.key === "Escape") { setShowDropdown(false); setSearch(""); }
  };

  const isSubmitting = createWithdrawal.isPending || createForContractor.isPending;

  const handleSubmit = async () => {
    if (items.length === 0) { toast.error("No items added"); return; }
    if (!jobId.trim()) { toast.error("Job ID is required"); return; }
    if (!serviceAddress.trim()) { toast.error("Service address is required"); return; }
    if (!isContractor && !selectedContractor) { toast.error("Please select a contractor"); return; }

    try {
      const payload = {
        items: items.map(({ product_id, sku, name, quantity, unit }) => ({
          product_id, sku, name, quantity, unit_price: 0, cost: 0, unit: unit || "each",
        })),
        job_id: jobId.trim(),
        service_address: serviceAddress.trim(),
        notes: notes.trim() || null,
      };

      if (isContractor) {
        await createWithdrawal.mutateAsync(payload);
      } else {
        await createForContractor.mutateAsync({ contractorId: selectedContractor, data: payload });
      }

      toast.success("Withdrawal logged — charged to account.");
      clearCart();
      setJobId("");
      setServiceAddress("");
      setNotes("");
      if (!isContractor) setSelectedContractor("");
    } catch (error) {
      const data = error.response?.data;
      if (data?.error_type === "insufficient_stock") {
        toast.error(`Not enough ${data.sku} — only ${data.available} available (you requested ${data.requested})`);
      } else {
        toast.error(getErrorMessage(error));
      }
    }
  };

  if (productsLoading || (!isContractor && contractorsLoading)) return <PageSkeleton />;

  return (
    <>
    <div className="max-w-3xl mx-auto p-8" data-testid="pos-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground tracking-tight">Issue Materials</h1>
        <p className="text-muted-foreground mt-1 text-sm">Log materials going out for a job</p>
      </div>

      <div className="bg-card border border-border rounded-xl p-6 mb-4 shadow-sm">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground mb-4">Job Details</p>
        <div className={`grid gap-4 ${!isContractor ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          {!isContractor && (
            <div>
              <Label className="text-muted-foreground font-medium text-sm mb-2 block"><HardHat className="w-4 h-4 inline mr-1" />Contractor</Label>
              <Select value={selectedContractor} onValueChange={setSelectedContractor}>
                <SelectTrigger data-testid="select-contractor"><SelectValue placeholder="Select contractor" /></SelectTrigger>
                <SelectContent>
                  {contractors.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}{c.company && <span className="text-muted-foreground text-xs ml-1">· {c.company}</span>}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground font-medium text-sm mb-2 block">Job ID *</Label>
            <JobPicker value={jobId} onChange={setJobId} required />
          </div>
          <div>
            <Label className="text-muted-foreground font-medium text-sm mb-2 block">Service Address *</Label>
            <AddressPicker value={serviceAddress} onChange={setServiceAddress} required />
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-6 mb-4 shadow-sm">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground mb-4">Add Items</p>
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground pointer-events-none" />
          <Input ref={searchRef} type="text" value={search} onChange={(e) => { setSearch(e.target.value); setShowDropdown(true); }} onFocus={() => search && setShowDropdown(true)} onKeyDown={handleSearchKeyDown} placeholder="Scan barcode or search by SKU / name…" className="pl-12 pr-12 w-full" autoFocus data-testid="item-search-input" />
          <ScanLine className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 pointer-events-none" />
          {showDropdown && search.trim().length > 0 && (
            <div ref={dropdownRef} className="absolute z-20 left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg overflow-hidden" data-testid="search-dropdown">
              {searchResults.length > 0 ? searchResults.map((product) => (
                <button key={product.id} onClick={() => handleAddItem(product)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted border-b border-border/50 last:border-b-0 text-left transition-colors" data-testid={`search-result-${product.sku}`}>
                  <div>
                    <span className="font-mono text-xs text-muted-foreground mr-2">{product.sku}</span>
                    <span className="font-medium text-foreground">{product.name}</span>
                  </div>
                  <div className="flex items-center gap-4 shrink-0 ml-4">
                    <span className="text-xs text-muted-foreground">{Math.floor(product.sell_quantity ?? product.quantity)} in stock</span>
                    <span className="font-semibold text-foreground tabular-nums">${(product.sell_price ?? product.price).toFixed(2)}<span className="text-xs font-normal text-muted-foreground ml-0.5">/{product.sell_uom || "ea"}</span></span>
                    <Plus className="w-4 h-4 text-muted-foreground/60" />
                  </div>
                </button>
              )) : (
                <div className="px-4 py-3 text-sm text-muted-foreground">No matching products in stock</div>
              )}
            </div>
          )}
        </div>
      </div>

      {items.length > 0 && (
        <div className="bg-card border border-border rounded-xl shadow-sm mb-4 overflow-hidden">
          <div className="px-6 py-4 border-b border-border/50">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">{items.length} item{items.length !== 1 ? "s" : ""}</p>
          </div>
          <div className="divide-y divide-border/50">
            {items.map((item) => (
              <div key={item.product_id} className="flex items-center gap-4 px-6 py-4" data-testid={`item-row-${item.sku}`}>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-muted-foreground">{item.sku}</p>
                  <p className="font-medium text-foreground truncate">{item.name}</p>
                  <p className="text-xs text-muted-foreground">${item.unit_price.toFixed(2)} / {item.unit}</p>
                </div>
                <QuantityControl value={item.quantity} onChange={(v) => updateQuantity(item.product_id, v)} max={item.max_quantity} unit={item.unit} />
                <div className="w-20 text-right shrink-0">
                  <p className="font-semibold text-foreground tabular-nums">${(item.quantity * item.unit_price).toFixed(2)}</p>
                </div>
                <button onClick={() => removeItem(item.product_id)} className="text-muted-foreground/60 hover:text-destructive transition-colors shrink-0" data-testid={`remove-item-${item.sku}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {items.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-5">
          <div>
            <Label className="text-muted-foreground font-medium text-sm mb-2 block">Notes (optional)</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any additional notes…" data-testid="notes-input" />
          </div>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted border border-border">
            <Clock className="w-5 h-5 text-muted-foreground shrink-0" />
            <div>
              <span className="font-semibold text-foreground text-sm">Charge to Account</span>
              <p className="text-xs text-muted-foreground">Tax and totals computed by backend. Invoice later via Xero.</p>
            </div>
          </div>
          <div className="flex items-end justify-between pt-2 border-t border-border/50">
            <div className="space-y-1 text-sm">
              <div className="flex gap-6 text-muted-foreground">
                <span className="w-20">Est. Subtotal</span>
                <span className="font-mono tabular-nums">${displaySubtotal.toFixed(2)}</span>
              </div>
              <p className="text-xs text-muted-foreground">Final total (incl. tax) calculated on submit</p>
            </div>
            <Button onClick={handleSubmit} disabled={isSubmitting} className="btn-primary h-12 px-8" data-testid="checkout-btn">
              {isSubmitting ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing…</>) : (<><Check className="w-4 h-4 mr-2" />Log Withdrawal</>)}
            </Button>
          </div>
        </div>
      )}
    </div>

    <UnknownBarcodeSheet
      open={!!unknownBarcode}
      onOpenChange={(open) => { if (!open) setUnknownBarcode(null); }}
      barcode={unknownBarcode}
      products={allProducts}
      onAddProduct={(product) => {
        addItem(product);
        toast.success(`Added: ${product.sku} (+1)`);
        setUnknownBarcode(null);
      }}
    />
    </>
  );
};

export default IssueMaterials;
