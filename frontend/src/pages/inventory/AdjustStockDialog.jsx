import { useState } from "react";
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
import { ADJUST_REASONS } from "@/lib/constants";
import { getErrorMessage } from "@/lib/api-client";
import { useAdjustStock } from "@/hooks/useProducts";

export function AdjustStockDialog({ product, open, onOpenChange }) {
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("correction");
  const adjustMutation = useAdjustStock();

  const handleSubmit = (e) => {
    e.preventDefault();
    const d = parseInt(delta, 10);
    if (isNaN(d) || d === 0) {
      toast.error("Enter a non-zero quantity delta");
      return;
    }
    if (!product) return;

    adjustMutation.mutate(
      { id: product.id, data: { quantity_delta: d, reason } },
      {
        onSuccess: () => {
          toast.success("Stock adjusted");
          setDelta("");
          setReason("correction");
          onOpenChange(false);
        },
        onError: (err) => toast.error(getErrorMessage(err)),
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust Stock</DialogTitle>
          {product && (
            <p className="text-sm text-slate-500">
              {product.sku} — {product.name}
            </p>
          )}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          <div>
            <Label>Quantity delta (positive to add, negative to remove)</Label>
            <Input
              type="number"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              placeholder="e.g. 5 or -3"
              className="input-workshop mt-2"
            />
          </div>
          <div>
            <Label>Reason</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger className="input-workshop mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADJUST_REASONS.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={adjustMutation.isPending}>
              {adjustMutation.isPending ? "Adjusting..." : "Adjust"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
