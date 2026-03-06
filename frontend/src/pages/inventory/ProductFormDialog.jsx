import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sparkles } from "lucide-react";
import { getErrorMessage } from "@/lib/api-client";
import api from "@/lib/api-client";
import { useCreateProduct, useUpdateProduct, useSuggestUom } from "@/hooks/useProducts";
import { ProductFields } from "@/components/ProductFields";

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

export function ProductFormDialog({
  open,
  onOpenChange,
  editingProduct,
  departments = [],
  vendors = [],
}) {
  const [form, setForm] = useState(INITIAL_FORM);
  const suggestTimeout = useRef(null);

  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct();
  const suggestMutation = useSuggestUom();
  const saving = createMutation.isPending || updateMutation.isPending;

  const skuPreviewEnabled = open && !editingProduct && !!form.department_id;
  const { data: skuPreviewData } = useQuery({
    queryKey: ["skuPreview", form.department_id, form.name],
    queryFn: () => {
      const params = { department_id: form.department_id };
      if (form.name?.trim()) params.product_name = form.name.trim();
      return api.sku.preview(params);
    },
    enabled: skuPreviewEnabled,
  });
  const skuPreview = skuPreviewData?.next_sku ?? null;

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
  }, [open, editingProduct]);

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
    const price = parseFloat(form.price);
    const cost = parseFloat(form.cost) || 0;
    if (isNaN(price) || price < 0) {
      toast.error("Price must be zero or greater");
      return;
    }
    if (cost < 0) {
      toast.error("Cost must be zero or greater");
      return;
    }

    const data = {
      name: form.name,
      description: form.description,
      price,
      cost,
      quantity: parseFloat(form.quantity) || 0,
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
          <div className={`rounded-lg px-4 py-3 ${editingProduct ? "bg-warning/10 border border-warning/30" : "bg-muted border border-border"}`}>
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">SKU</p>
              {editingProduct && (
                <span className="text-[10px] font-medium text-accent uppercase tracking-wider">Cannot be changed</span>
              )}
            </div>
            {editingProduct ? (
              <p className="font-mono text-lg font-semibold text-foreground">{editingProduct.sku}</p>
            ) : skuPreview ? (
              <p className="font-mono text-lg font-semibold text-foreground">
                {skuPreview}
                <span className="text-xs font-normal text-muted-foreground ml-2">(assigned on save)</span>
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Select a department to see SKU</p>
            )}
          </div>

          <ProductFields
            fields={form}
            onChange={(name, value) => {
              if (name === "name") { handleNameChange(value); return; }
              setForm((f) => ({ ...f, [name]: value }));
            }}
            departments={departments}
            vendors={vendors}
            uomAction={
              <Button
                type="button"
                variant="outline"
                onClick={suggestUnit}
                disabled={suggestMutation.isPending || !form.name?.trim()}
                className="h-11 px-3 border-border mt-2"
                title="Use AI to suggest unit from product name"
              >
                {suggestMutation.isPending ? (
                  <span className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin block" />
                ) : (
                  <Sparkles className="w-5 h-5 text-accent" />
                )}
                <span className="ml-2 text-sm">Suggest unit</span>
              </Button>
            }
          />

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
