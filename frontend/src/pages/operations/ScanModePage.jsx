import { useState } from "react";
import { toast } from "sonner";
import { Send, Trash2, ScanLine, CheckCircle2, Loader2, Camera, Keyboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QuantityControl } from "@/components/QuantityControl";
import { UnknownBarcodeSheet } from "@/components/UnknownBarcodeSheet";
import { CameraScanner } from "@/components/CameraScanner";
import { JobPicker } from "@/components/JobPicker";
import { AddressPicker } from "@/components/AddressPicker";
import { useBarcodeScanner } from "@/hooks/useBarcodeScanner";
import { useCart } from "@/hooks/useCart";
import { useProducts } from "@/hooks/useProducts";
import { useCreateWithdrawal } from "@/hooks/useWithdrawals";
import { getErrorMessage } from "@/lib/api-client";

/**
 * Full-screen iPad-optimised scan-and-checkout kiosk.
 *
 * Camera is the primary input; manual text entry is the fallback.
 * Creates direct withdrawals (not material requests) with job linkage.
 * Accessible at /scan for contractors and warehouse roles.
 */
const ScanModePage = () => {
  const [lastScanned, setLastScanned] = useState(null);
  const [unknownBarcode, setUnknownBarcode] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [cameraMode, setCameraMode] = useState(true);
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");

  const { items, addItem, updateQuantity, removeItem, clear: clearCart, total: subtotal } = useCart({ persist: true });
  const { data: productsData } = useProducts();
  const allProducts = Array.isArray(productsData) ? productsData : (productsData?.items || []);
  const createWithdrawal = useCreateWithdrawal();

  const scanner = useBarcodeScanner({
    onSuccess: (product) => {
      if ((product.sell_quantity ?? product.quantity) <= 0) {
        toast.error("Out of stock");
        setLastScanned({ sku: product.sku, status: "out_of_stock" });
        return;
      }
      addItem(product);
      setLastScanned({ sku: product.sku, name: product.name, status: "added" });
    },
    onNotFound: ({ barcode }) => {
      setUnknownBarcode(barcode);
      setLastScanned({ sku: barcode, status: "not_found" });
    },
    onInvalidCheckDigit: (barcode) => {
      toast.error("Bad check digit");
      setLastScanned({ sku: barcode, status: "invalid" });
    },
  });

  const handleSubmit = async () => {
    if (items.length === 0) { toast.error("Cart is empty"); return; }
    if (!jobId.trim()) { toast.error("Job ID is required"); return; }
    if (!serviceAddress.trim()) { toast.error("Service address is required"); return; }
    setSubmitting(true);
    try {
      await createWithdrawal.mutateAsync({
        items: items.map(({ product_id, sku, name, quantity, unit_price, unit }) => ({
          product_id, sku, name, quantity, unit_price, cost: 0,
          subtotal: quantity * unit_price, unit: unit || "each",
        })),
        job_id: jobId.trim(),
        service_address: serviceAddress.trim(),
      });
      toast.success("Withdrawal logged!");
      clearCart();
      setLastScanned(null);
      setJobId("");
      setServiceAddress("");
    } catch (err) {
      const data = err.response?.data;
      if (data?.error_type === "insufficient_stock") {
        toast.error(`Not enough ${data.sku} — only ${data.available} available`);
      } else {
        toast.error(getErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
      if (!cameraMode) scanner.inputRef.current?.focus();
    }
  };

  const statusConfig = {
    added:        { color: "text-success", bg: "bg-success/10 border-success/30", label: "Added" },
    not_found:    { color: "text-accent",  bg: "bg-warning/10 border-warning/30", label: "Not found" },
    invalid:      { color: "text-destructive", bg: "bg-destructive/10 border-destructive/30", label: "Invalid barcode" },
    out_of_stock: { color: "text-muted-foreground", bg: "bg-muted border-border", label: "Out of stock" },
  };

  const status = lastScanned ? statusConfig[lastScanned.status] : null;
  const canSubmit = items.length > 0 && jobId.trim() && serviceAddress.trim();

  return (
    <div className="flex flex-col h-screen bg-muted">

      {/* ── Job details + scan mode ── */}
      <div className="flex-shrink-0 bg-card border-b border-border px-6 pt-4 pb-3">
        <div className="max-w-xl mx-auto space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-muted-foreground text-xs font-medium mb-1 block">Job *</Label>
              <JobPicker value={jobId} onChange={setJobId} required />
            </div>
            <div>
              <Label className="text-muted-foreground text-xs font-medium mb-1 block">Address *</Label>
              <AddressPicker value={serviceAddress} onChange={setServiceAddress} required />
            </div>
          </div>

          {/* Mode toggle */}
          <div className="flex gap-1 bg-muted rounded-lg p-1">
            <button
              onClick={() => setCameraMode(true)}
              className={`flex-1 flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                cameraMode ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Camera className="w-4 h-4" />Camera
            </button>
            <button
              onClick={() => setCameraMode(false)}
              className={`flex-1 flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                !cameraMode ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Keyboard className="w-4 h-4" />Manual
            </button>
          </div>
        </div>
      </div>

      {/* ── Scanner area ── */}
      <div className="flex-shrink-0 bg-card border-b border-border p-4">
        <div className="max-w-xl mx-auto">
          {cameraMode ? (
            <CameraScanner
              onScan={(code) => scanner.submit(code)}
              onClose={() => setCameraMode(false)}
              scanning={scanner.scanning}
            />
          ) : (
            <>
              <div className={`rounded-2xl border-2 p-5 mb-2 transition-colors ${status ? status.bg : "bg-muted border-border"}`}>
                <div className="flex items-center gap-3 mb-3">
                  <ScanLine className={`w-6 h-6 ${status ? status.color : "text-muted-foreground"}`} />
                  <span className={`font-semibold text-lg ${status ? status.color : "text-muted-foreground"}`}>
                    {lastScanned
                      ? `${status?.label}: ${lastScanned.name || lastScanned.sku}`
                      : "Ready to scan…"}
                  </span>
                </div>
                <Input
                  ref={scanner.inputRef}
                  type="text"
                  value={scanner.value}
                  onChange={(e) => scanner.setValue(e.target.value)}
                  onKeyDown={scanner.onKeyDown}
                  placeholder="Scan barcode or type SKU…"
                  className="text-lg h-14 font-mono text-center tracking-widest"
                  autoFocus
                  disabled={scanner.scanning}
                />
              </div>
              <p className="text-xs text-center text-muted-foreground">
                {scanner.scanning ? "Looking up…" : "Type a barcode or SKU and press Enter"}
              </p>
            </>
          )}

          {/* Status badge for camera mode */}
          {cameraMode && lastScanned && status && (
            <div className={`mt-3 rounded-xl border-2 px-4 py-2.5 flex items-center gap-2 ${status.bg}`}>
              <ScanLine className={`w-4 h-4 ${status.color}`} />
              <span className={`text-sm font-medium ${status.color}`}>
                {status.label}: {lastScanned.name || lastScanned.sku}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── Cart ── */}
      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-xl mx-auto">
          {items.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Scan items to add them to your cart</p>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div key={item.product_id} className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[10px] text-muted-foreground">{item.sku}</p>
                    <p className="font-medium text-foreground truncate">{item.name}</p>
                  </div>
                  <QuantityControl
                    value={item.quantity}
                    onChange={(v) => updateQuantity(item.product_id, v)}
                    max={item.max_quantity}
                  />
                  <button onClick={() => removeItem(item.product_id)} className="text-muted-foreground/60 hover:text-destructive transition-colors p-1">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="flex-shrink-0 bg-card border-t border-border p-4 safe-area-bottom">
        <div className="max-w-xl mx-auto flex items-center gap-4">
          <div className="flex-1">
            <p className="text-xs text-muted-foreground">{items.length} item{items.length !== 1 ? "s" : ""}</p>
            <p className="font-semibold text-foreground tabular-nums">${subtotal.toFixed(2)}</p>
          </div>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit || submitting}
            className="btn-primary h-14 px-10 text-base"
          >
            {submitting
              ? <><Loader2 className="w-5 h-5 mr-2 animate-spin" />Processing…</>
              : <><Send className="w-5 h-5 mr-2" />Checkout</>}
          </Button>
        </div>
      </div>

      <UnknownBarcodeSheet
        open={!!unknownBarcode}
        onOpenChange={(open) => { if (!open) setUnknownBarcode(null); }}
        barcode={unknownBarcode}
        products={allProducts}
        onAddProduct={(product) => {
          addItem(product);
          setLastScanned({ sku: product.sku, name: product.name, status: "added" });
          toast.success(`Added: ${product.sku} (+1)`);
          setUnknownBarcode(null);
        }}
      />
    </div>
  );
};

export default ScanModePage;
