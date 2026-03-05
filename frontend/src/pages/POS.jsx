import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Search, Trash2, Check, HardHat, MapPin, FileText, Clock, Loader2, ScanLine, Plus } from "lucide-react";
import { PageSkeleton } from "@/components/LoadingSkeleton";
import { QuantityControl } from "@/components/QuantityControl";
import { StatusBadge } from "@/components/StatusBadge";
import { useProducts } from "@/hooks/useProducts";
import { useContractors } from "@/hooks/useContractors";
import { useCreateWithdrawal, useCreateWithdrawalForContractor } from "@/hooks/useWithdrawals";
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

  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [selectedContractor, setSelectedContractor] = useState("");
  const [jobId, setJobId] = useState("");
  const [serviceAddress, setServiceAddress] = useState("");
  const [notes, setNotes] = useState("");

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

  const addItem = (product) => {
    const sellQty = product.sell_quantity ?? product.quantity;
    const existing = items.find((i) => i.product_id === product.id);
    if (existing) {
      if (existing.quantity >= sellQty) { toast.error("Not enough stock"); return; }
      setItems(items.map((i) => i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i));
    } else {
      setItems([...items, {
        product_id: product.id,
        sku: product.sku,
        name: product.name,
        quantity: 1,
        max_quantity: sellQty,
        unit: product.sell_uom || "each",
        display_price: product.sell_price ?? product.price,
      }]);
    }
    setSearch("");
    setShowDropdown(false);
    searchRef.current?.focus();
  };

  const updateQuantity = (productId, newQty) => {
    setItems(items.map((item) => {
      if (item.product_id !== productId) return item;
      if (newQty <= 0) return null;
      if (newQty > item.max_quantity) { toast.error("Not enough stock"); return item; }
      return { ...item, quantity: newQty };
    }).filter(Boolean));
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "Enter" && searchResults.length > 0) {
      const exact = searchResults.find((p) => p.sku.toLowerCase() === search.toLowerCase());
      addItem(exact || searchResults[0]);
    }
    if (e.key === "Escape") { setShowDropdown(false); setSearch(""); }
  };

  const displaySubtotal = items.reduce((sum, i) => sum + i.quantity * i.display_price, 0);

  const handleSubmit = async () => {
    if (items.length === 0) { toast.error("No items added"); return; }
    if (!jobId.trim()) { toast.error("Job ID is required"); return; }
    if (!serviceAddress.trim()) { toast.error("Service address is required"); return; }
    if (!isContractor && !selectedContractor) { toast.error("Please select a contractor"); return; }

    setProcessing(true);
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
      setItems([]);
      setJobId("");
      setServiceAddress("");
      setNotes("");
      if (!isContractor) setSelectedContractor("");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setProcessing(false);
    }
  };

  if (productsLoading || (!isContractor && contractorsLoading)) return <PageSkeleton />;

  return (
    <div className="max-w-3xl mx-auto p-8" data-testid="pos-page">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">Issue Materials</h1>
        <p className="text-slate-500 mt-1 text-sm">Log materials going out for a job</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4 shadow-sm">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-4">Job Details</p>
        <div className={`grid gap-4 ${!isContractor ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          {!isContractor && (
            <div>
              <Label className="text-slate-600 font-medium text-sm mb-2 block"><HardHat className="w-4 h-4 inline mr-1" />Contractor</Label>
              <Select value={selectedContractor} onValueChange={setSelectedContractor}>
                <SelectTrigger data-testid="select-contractor"><SelectValue placeholder="Select contractor" /></SelectTrigger>
                <SelectContent>
                  {contractors.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}{c.company && <span className="text-slate-400 text-xs ml-1">· {c.company}</span>}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label className="text-slate-600 font-medium text-sm mb-2 block"><FileText className="w-4 h-4 inline mr-1" />Job ID *</Label>
            <Input value={jobId} onChange={(e) => setJobId(e.target.value)} placeholder="e.g. JOB-2024-001" data-testid="job-id-input" />
          </div>
          <div>
            <Label className="text-slate-600 font-medium text-sm mb-2 block"><MapPin className="w-4 h-4 inline mr-1" />Service Address *</Label>
            <Input value={serviceAddress} onChange={(e) => setServiceAddress(e.target.value)} placeholder="Where are these going?" data-testid="service-address-input" />
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4 shadow-sm">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 mb-4">Add Items</p>
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400 pointer-events-none" />
          <Input ref={searchRef} type="text" value={search} onChange={(e) => { setSearch(e.target.value); setShowDropdown(true); }} onFocus={() => search && setShowDropdown(true)} onKeyDown={handleSearchKeyDown} placeholder="Scan barcode or search by SKU / name…" className="pl-12 pr-12 w-full" autoFocus data-testid="item-search-input" />
          <ScanLine className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300 pointer-events-none" />
          {showDropdown && search.trim().length > 0 && (
            <div ref={dropdownRef} className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden" data-testid="search-dropdown">
              {searchResults.length > 0 ? searchResults.map((product) => (
                <button key={product.id} onClick={() => addItem(product)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 border-b border-slate-100 last:border-b-0 text-left transition-colors" data-testid={`search-result-${product.sku}`}>
                  <div>
                    <span className="font-mono text-xs text-slate-400 mr-2">{product.sku}</span>
                    <span className="font-medium text-slate-900">{product.name}</span>
                  </div>
                  <div className="flex items-center gap-4 shrink-0 ml-4">
                    <span className="text-xs text-slate-400">{Math.floor(product.sell_quantity ?? product.quantity)} in stock</span>
                    <span className="font-semibold text-slate-700 tabular-nums">${(product.sell_price ?? product.price).toFixed(2)}<span className="text-xs font-normal text-slate-400 ml-0.5">/{product.sell_uom || "ea"}</span></span>
                    <Plus className="w-4 h-4 text-slate-300" />
                  </div>
                </button>
              )) : (
                <div className="px-4 py-3 text-sm text-slate-400">No matching products in stock</div>
              )}
            </div>
          )}
        </div>
      </div>

      {items.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm mb-4 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{items.length} item{items.length !== 1 ? "s" : ""}</p>
          </div>
          <div className="divide-y divide-slate-100">
            {items.map((item) => (
              <div key={item.product_id} className="flex items-center gap-4 px-6 py-4" data-testid={`item-row-${item.sku}`}>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-slate-400">{item.sku}</p>
                  <p className="font-medium text-slate-900 truncate">{item.name}</p>
                  <p className="text-xs text-slate-400">${item.display_price.toFixed(2)} / {item.unit}</p>
                </div>
                <QuantityControl value={item.quantity} onChange={(v) => updateQuantity(item.product_id, v)} max={item.max_quantity} unit={item.unit} />
                <div className="w-20 text-right shrink-0">
                  <p className="font-semibold text-slate-900 tabular-nums">${(item.quantity * item.display_price).toFixed(2)}</p>
                </div>
                <button onClick={() => setItems(items.filter((i) => i.product_id !== item.product_id))} className="text-slate-300 hover:text-red-500 transition-colors shrink-0" data-testid={`remove-item-${item.sku}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {items.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-5">
          <div>
            <Label className="text-slate-600 font-medium text-sm mb-2 block">Notes (optional)</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any additional notes…" data-testid="notes-input" />
          </div>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
            <Clock className="w-5 h-5 text-slate-400 shrink-0" />
            <div>
              <span className="font-semibold text-slate-900 text-sm">Charge to Account</span>
              <p className="text-xs text-slate-500">Tax and totals computed by backend. Invoice later via Xero.</p>
            </div>
          </div>
          <div className="flex items-end justify-between pt-2 border-t border-slate-100">
            <div className="space-y-1 text-sm">
              <div className="flex gap-6 text-slate-500">
                <span className="w-20">Est. Subtotal</span>
                <span className="font-mono tabular-nums">${displaySubtotal.toFixed(2)}</span>
              </div>
              <p className="text-xs text-slate-400">Final total (incl. tax) calculated on submit</p>
            </div>
            <Button onClick={handleSubmit} disabled={processing} className="btn-primary h-12 px-8" data-testid="checkout-btn">
              {processing ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing…</>) : (<><Check className="w-4 h-4 mr-2" />Log Withdrawal</>)}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default IssueMaterials;
