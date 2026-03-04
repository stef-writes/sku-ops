import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sparkles, Info } from "lucide-react";
import { UOM_OPTIONS } from "@/lib/constants";
import { getErrorMessage } from "@/lib/api-client";
import api from "@/lib/api-client";
import { useCreateProduct, useUpdateProduct, useSuggestUom } from "@/hooks/useProducts";

const INITIAL_FORM = {
  name: "",
  description: "",
  price: "",
  cost: "",
  quantity: "",
  min_stock: "5",
  department_id: "",
  vendor_id: "",
  barcode: "",
  base_unit: "each",
  sell_uom: "each",
  pack_qty: "1",
};

function FieldTip({ children }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="w-3.5 h-3.5 text-slate-400 cursor-help inline-block ml-1 align-middle" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[220px] text-center">
        {children}
      </TooltipContent>
    </Tooltip>
  );
}

export function ProductFormDialog({
  open,
  onOpenChange,
  editingProduct,
  departments = [],
  vendors = [],
}) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [skuPreview, setSkuPreview] = useState(null);
  const suggestTimeout = useRef(null);

  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct();
  const suggestMutation = useSuggestUom();
  const saving = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!open) return;
    if (editingProduct) {
      setForm({
        name: editingProduct.name,
        description: editingProduct.description || "",
        price: editingProduct.price.toString(),
        cost: editingProduct.cost?.toString() || "",
        quantity: editingProduct.quantity.toString(),
        min_stock: editingProduct.min_stock?.toString() || "5",
        department_id: editingProduct.department_id,
        vendor_id: editingProduct.vendor_id || "",
        barcode: editingProduct.barcode || "",
        base_unit: editingProduct.base_unit || "each",
        sell_uom: editingProduct.sell_uom || "each",
        pack_qty: String(editingProduct.pack_qty ?? 1),
      });
    } else {
      setForm(INITIAL_FORM);
    }
    setSkuPreview(null);
  }, [open, editingProduct]);

  useEffect(() => {
    if (!open || editingProduct || !form.department_id) {
      setSkuPreview(null);
      return;
    }
    const params = { department_id: form.department_id };
    if (form.name?.trim()) params.product_name = form.name.trim();
    api.sku.preview(params).then((d) => setSkuPreview(d.next_sku)).catch(() => setSkuPreview(null));
  }, [open, editingProduct, form.department_id, form.name]);

  useEffect(() => {
    return () => {
      if (suggestTimeout.current) clearTimeout(suggestTimeout.current);
    };
  }, []);

  const handleNameChange = (v) => {
    setForm((f) => ({ ...f, name: v }));
    if (suggestTimeout.current) clearTimeout(suggestTimeout.current);
    if (!editingProduct && v.trim().length >= 3) {
      suggestTimeout.current = setTimeout(() => {
        suggestMutation.mutate(
          { name: v.trim() },
          {
            onSuccess: (data) => {
              setForm((f) => ({
                ...f,
                base_unit: data.base_unit || "each",
                sell_uom: data.sell_uom || "each",
                pack_qty: String(data.pack_qty ?? 1),
              }));
            },
          }
        );
        suggestTimeout.current = null;
      }, 600);
    }
  };

  const suggestUnit = useCallback(() => {
    if (!form.name?.trim()) {
      toast.error("Enter a product name first");
      return;
    }
    suggestMutation.mutate(
      { name: form.name.trim(), description: form.description?.trim() || undefined },
      {
        onSuccess: (data) => {
          setForm((f) => ({
            ...f,
            base_unit: data.base_unit || "each",
            sell_uom: data.sell_uom || "each",
            pack_qty: String(data.pack_qty ?? 1),
          }));
          toast.success("Unit suggested");
        },
        onError: (err) => toast.error(getErrorMessage(err)),
      }
    );
  }, [form.name, form.description, suggestMutation]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.price || !form.department_id) {
      toast.error("Please fill in required fields");
      return;
    }

    const data = {
      name: form.name,
      description: form.description,
      price: parseFloat(form.price),
      cost: parseFloat(form.cost) || 0,
      quantity: parseInt(form.quantity) || 0,
      min_stock: parseInt(form.min_stock) || 5,
      department_id: form.department_id,
      vendor_id: form.vendor_id || null,
      barcode: form.barcode || null,
      base_unit: form.base_unit || "each",
      sell_uom: form.sell_uom || "each",
      pack_qty: parseInt(form.pack_qty) || 1,
    };

    const mutation = editingProduct ? updateMutation : createMutation;
    const mutationArg = editingProduct ? { id: editingProduct.id, data } : data;

    mutation.mutate(mutationArg, {
      onSuccess: (result) => {
        toast.success(editingProduct ? "Product updated!" : `Product created with SKU ${result?.sku ?? ""}`);
        onOpenChange(false);
      },
      onError: (err) => toast.error(getErrorMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg rounded-2xl" data-testid="product-dialog">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold">
            {editingProduct ? "Edit product" : "Add new product"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          <div className={`rounded-lg px-4 py-3 ${editingProduct ? "bg-amber-50/50 border border-amber-200/60" : "bg-slate-50 border border-slate-200"}`}>
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">SKU</p>
              {editingProduct && (
                <span className="text-[10px] font-medium text-amber-700 uppercase tracking-wider">Cannot be changed</span>
              )}
            </div>
            {editingProduct ? (
              <p className="font-mono text-lg font-semibold text-slate-900">{editingProduct.sku}</p>
            ) : skuPreview ? (
              <p className="font-mono text-lg font-semibold text-slate-700">
                {skuPreview}
                <span className="text-xs font-normal text-slate-400 ml-2">(assigned on save)</span>
              </p>
            ) : (
              <p className="text-sm text-slate-400">Select a department to see SKU</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label className="text-slate-600 font-medium text-sm">Product name *</Label>
              <Input
                value={form.name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="e.g., 2x4 Pine Board, 5 Gal Paint"
                className="input-workshop mt-2"
                data-testid="product-name-input"
              />
            </div>

            <div className="col-span-2">
              <Label className="text-slate-600 font-medium text-sm">Description</Label>
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional description"
                className="input-workshop mt-2"
                data-testid="product-description-input"
              />
            </div>

            <div>
              <Label className="text-slate-600 font-medium text-sm">Department *</Label>
              <Select value={form.department_id} onValueChange={(value) => setForm({ ...form, department_id: value })}>
                <SelectTrigger className="input-workshop mt-2" data-testid="product-department-select">
                  <SelectValue placeholder="Select department" />
                </SelectTrigger>
                <SelectContent>
                  {departments.map((dept) => (
                    <SelectItem key={dept.id} value={dept.id}>
                      <span className="font-mono font-medium">{dept.code}</span>
                      <span className="text-slate-400 mx-1.5">—</span>
                      {dept.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-slate-600 font-medium text-sm">Vendor</Label>
              <Select value={form.vendor_id || "none"} onValueChange={(value) => setForm({ ...form, vendor_id: value === "none" ? "" : value })}>
                <SelectTrigger className="input-workshop mt-2" data-testid="product-vendor-select">
                  <SelectValue placeholder="Select vendor" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {vendors.map((vendor) => (
                    <SelectItem key={vendor.id} value={vendor.id}>{vendor.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-slate-600 font-medium text-sm">Price *</Label>
              <Input type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="0.00" className="input-workshop mt-2" data-testid="product-price-input" />
            </div>
            <div>
              <Label className="text-slate-600 font-medium text-sm">Cost</Label>
              <Input type="number" step="0.01" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} placeholder="0.00" className="input-workshop mt-2" data-testid="product-cost-input" />
            </div>
            <div>
              <Label className="text-slate-600 font-medium text-sm">Quantity</Label>
              <Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} placeholder="0" className="input-workshop mt-2" data-testid="product-quantity-input" />
            </div>
            <div>
              <Label className="text-slate-600 font-medium text-sm">
                Min stock level
                <FieldTip>Alert threshold — item shows as Low Stock when quantity falls to or below this number.</FieldTip>
              </Label>
              <Input type="number" value={form.min_stock} onChange={(e) => setForm({ ...form, min_stock: e.target.value })} placeholder="5" className="input-workshop mt-2" data-testid="product-min-stock-input" />
            </div>

            <div className="col-span-3 flex items-end gap-2 flex-wrap">
              <div className="flex-1 min-w-[100px]">
                <Label className="text-slate-600 font-medium text-sm">
                  Base Unit
                  <FieldTip>The physical unit this product is stored and counted in (e.g. each, roll, gallon).</FieldTip>
                </Label>
                <Select value={form.base_unit} onValueChange={(v) => setForm({ ...form, base_unit: v })}>
                  <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1 min-w-[100px]">
                <Label className="text-slate-600 font-medium text-sm">
                  Sell Unit
                  <FieldTip>The unit shown to customers and used when issuing materials (e.g. box, case). Can differ from Base Unit.</FieldTip>
                </Label>
                <Select value={form.sell_uom} onValueChange={(v) => setForm({ ...form, sell_uom: v })}>
                  <SelectTrigger className="input-workshop mt-2"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {UOM_OPTIONS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="min-w-[80px]">
                <Label className="text-slate-600 font-medium text-sm">
                  Pack Qty
                  <FieldTip>How many Base Units are in one Sell Unit. E.g. a box of 12 screws → Pack Qty = 12.</FieldTip>
                </Label>
                <Input type="number" min="1" value={form.pack_qty} onChange={(e) => setForm({ ...form, pack_qty: e.target.value })} className="input-workshop mt-2" />
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={suggestUnit}
                disabled={suggestMutation.isPending || !form.name?.trim()}
                className="h-11 px-3 border-slate-200 mt-2"
                title="Use AI to suggest unit from product name"
              >
                {suggestMutation.isPending ? (
                  <span className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin block" />
                ) : (
                  <Sparkles className="w-5 h-5 text-amber-500" />
                )}
                <span className="ml-2 text-sm">Suggest unit</span>
              </Button>
            </div>

            <div className="col-span-2">
              <Label className="text-slate-600 font-medium text-sm">Barcode</Label>
              <Input
                value={form.barcode}
                onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                placeholder="UPC (12 digits) or leave blank to use SKU"
                className="input-workshop mt-2"
                data-testid="product-barcode-input"
              />
              <p className="text-xs text-slate-500 mt-1">
                UPC for vendor products; leave blank to use internal SKU (Code128)
              </p>
            </div>
          </div>

          <div className="flex gap-3 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} className="flex-1 btn-secondary h-12" data-testid="product-cancel-btn">
              Cancel
            </Button>
            <Button type="submit" disabled={saving} className="flex-1 btn-primary h-12" data-testid="product-save-btn">
              {saving ? "Saving..." : editingProduct ? "Update Product" : "Create Product"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
