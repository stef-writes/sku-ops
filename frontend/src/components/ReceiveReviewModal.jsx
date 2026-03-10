import { useState, useEffect, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Package, ArrowRight } from "lucide-react";
import { useProductMatch } from "@/hooks/useProductMatch";
import { ProductMatchPicker } from "@/components/ProductMatchPicker";
import { ProductFields } from "@/components/ProductFields";

const COMPACT_HIDDEN = new Set([
  "description",
  "vendor_id",
  "min_stock",
  "quantity",
]);

export function ReceiveReviewModal({
  open,
  onOpenChange,
  items: rawItems,
  departments = [],
  onConfirm,
  isSubmitting = false,
}) {
  const [items, setItems] = useState([]);
  const { matches, autoMatch, searchMatch, confirmMatch, clearMatch, reset } =
    useProductMatch();

  useEffect(() => {
    if (!open || !rawItems?.length) {
      setItems([]);
      reset();
      return;
    }

    const seeded = rawItems.map((item) => ({
      ...item,
      _delivered_qty:
        item._delivered_qty ?? item.delivered_qty ?? item.ordered_qty ?? 1,
      _cost: item.cost > 0 ? item.cost : "",
    }));
    setItems(seeded);

    const preMatched = [];
    const needMatch = [];
    for (const item of seeded) {
      if (item.product_id && item.matched_sku) {
        preMatched.push(item);
      } else {
        needMatch.push(item);
      }
    }

    for (const item of preMatched) {
      confirmMatch(item.id, {
        id: item.product_id,
        sku: item.matched_sku,
        name: item.matched_name || item.name,
        quantity: item.matched_quantity ?? 0,
        cost: item.matched_cost ?? item.cost,
      });
    }

    if (needMatch.length > 0) {
      autoMatch(needMatch);
    }
  }, [open, rawItems]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateItem = (itemId, field, value) => {
    setItems((prev) =>
      prev.map((it) => (it.id === itemId ? { ...it, [field]: value } : it)),
    );
  };

  const handleMatchConfirm = (itemId, product) => {
    confirmMatch(itemId, product);
  };

  const handleMatchClear = (itemId) => {
    clearMatch(itemId);
  };

  const resolvedItems = useMemo(() => {
    return items.map((item) => {
      const m = matches[item.id];
      const matched = m?.matched || null;
      return { ...item, _resolved_match: matched };
    });
  }, [items, matches]);

  const matchedItems = resolvedItems.filter((i) => i._resolved_match);
  const newItems = resolvedItems.filter((i) => !i._resolved_match);

  const handleConfirm = () => {
    const payload = resolvedItems.map((it) => {
      const entry = {
        id: it.id,
        delivered_qty: parseFloat(it._delivered_qty) || 1,
      };
      if (it._cost !== "" && it._cost != null)
        entry.cost = parseFloat(it._cost);

      const matched = it._resolved_match;
      if (matched) {
        entry.product_id = matched.id;
      } else {
        if (it._name && it._name !== it.name) entry.name = it._name;
        if (it._unit_price != null && it._unit_price !== "")
          entry.unit_price = parseFloat(it._unit_price);
        if (it._suggested_department)
          entry.suggested_department = it._suggested_department;
        if (it._base_unit) entry.base_unit = it._base_unit;
        if (it._sell_uom) entry.sell_uom = it._sell_uom;
        if (it._pack_qty != null) entry.pack_qty = parseInt(it._pack_qty) || 1;
        if (it._barcode) entry.barcode = it._barcode;
      }

      return entry;
    });
    onConfirm?.(payload);
  };

  const totalCost = resolvedItems.reduce((sum, it) => {
    const qty = parseFloat(it._delivered_qty) || 0;
    const cost = parseFloat(it._cost) || parseFloat(it.cost) || 0;
    return sum + qty * cost;
  }, 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl rounded-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg font-semibold">
            <Package className="w-5 h-5 text-muted-foreground" />
            Review before receiving
          </DialogTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Match items to existing products or create new ones. Verify details
            before adding to inventory.
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-auto space-y-5 py-2">
          {matchedItems.length > 0 && (
            <div className="space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-success">
                Matched — will update existing stock ({matchedItems.length})
              </p>
              {matchedItems.map((item) => (
                <MatchedCard
                  key={item.id}
                  item={item}
                  matchState={matches[item.id] || {}}
                  onSearch={(q) => searchMatch(item.id, q)}
                  onConfirmMatch={(p) => handleMatchConfirm(item.id, p)}
                  onClearMatch={() => handleMatchClear(item.id)}
                  onChange={(field, val) => updateItem(item.id, field, val)}
                />
              ))}
            </div>
          )}

          {newItems.length > 0 && (
            <div className="space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-warning">
                New — will create product ({newItems.length})
              </p>
              {newItems.map((item) => (
                <NewCard
                  key={item.id}
                  item={item}
                  matchState={matches[item.id] || {}}
                  departments={departments}
                  onSearch={(q) => searchMatch(item.id, q)}
                  onConfirmMatch={(p) => handleMatchConfirm(item.id, p)}
                  onClearMatch={() => handleMatchClear(item.id)}
                  onChange={(field, val) => updateItem(item.id, field, val)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-border/50 pt-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {resolvedItems.length} item{resolvedItems.length !== 1 ? "s" : ""}
              {matchedItems.length > 0 &&
                ` (${matchedItems.length} matched, ${newItems.length} new)`}
            </span>
            {totalCost > 0 && (
              <span className="font-mono text-foreground">
                Est. cost: ${totalCost.toFixed(2)}
              </span>
            )}
          </div>
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="flex-1 h-11"
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={isSubmitting || resolvedItems.length === 0}
              className="flex-1 h-11 btn-primary"
            >
              {isSubmitting ? "Receiving…" : "Confirm & Receive"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function MatchedCard({
  item,
  matchState,
  onSearch,
  onConfirmMatch,
  onClearMatch,
  onChange,
}) {
  const matched = item._resolved_match;
  const currentQty = matched?.quantity ?? 0;
  const deliveredQty = parseFloat(item._delivered_qty) || 0;
  const newQty = currentQty + deliveredQty;

  return (
    <div className="p-4 rounded-xl border border-success/30 bg-success/10 space-y-3">
      <ProductMatchPicker
        matched={matched}
        options={matchState.options || []}
        searching={matchState.searching || false}
        onSearch={onSearch}
        onConfirm={onConfirmMatch}
        onClear={onClearMatch}
      />

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div className="bg-card rounded-lg border border-border px-3 py-2">
          <p className="text-[10px] font-medium text-muted-foreground uppercase">
            Current stock
          </p>
          <p className="font-mono font-semibold text-foreground">
            {currentQty}
          </p>
        </div>
        <div className="flex items-center justify-center">
          <ArrowRight className="w-4 h-4 text-muted-foreground/60" />
        </div>
        <div className="bg-card rounded-lg border border-success/30 px-3 py-2">
          <p className="text-[10px] font-medium text-success uppercase">
            New stock
          </p>
          <p className="font-mono font-semibold text-success">{newQty}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-muted-foreground text-xs">Delivered qty</Label>
          <Input
            type="number"
            min="0"
            step="any"
            value={item._delivered_qty}
            onChange={(e) => onChange("_delivered_qty", e.target.value)}
            className="h-9 text-sm mt-1"
          />
        </div>
        <div>
          <Label className="text-muted-foreground text-xs">
            Cost (for WAC)
          </Label>
          <Input
            type="number"
            step="0.01"
            value={item._cost ?? ""}
            onChange={(e) => onChange("_cost", e.target.value)}
            className="h-9 text-sm mt-1"
            placeholder={String(item.cost || "")}
          />
        </div>
      </div>
    </div>
  );
}

function NewCard({
  item,
  matchState,
  departments,
  onSearch,
  onConfirmMatch,
  onClearMatch,
  onChange,
}) {
  return (
    <div className="p-4 rounded-xl border border-warning/30 bg-warning/10 space-y-3">
      <ProductMatchPicker
        matched={null}
        options={matchState.options || []}
        searching={matchState.searching || false}
        onSearch={onSearch}
        onConfirm={onConfirmMatch}
        onClear={onClearMatch}
      />

      <ProductFields
        compact
        fields={{
          name: item._name ?? item.name ?? "",
          price: item._unit_price ?? item.unit_price ?? "",
          cost: item._cost ?? item.cost ?? "",
          base_unit: item._base_unit ?? item.base_unit ?? "each",
          sell_uom: item._sell_uom ?? item.sell_uom ?? "each",
          pack_qty: item._pack_qty ?? item.pack_qty ?? 1,
          barcode: item._barcode ?? "",
          department_id:
            item._suggested_department ?? item.suggested_department ?? "",
          quantity: item._delivered_qty ?? item.delivered_qty ?? 1,
        }}
        onChange={(field, value) => {
          const fieldMap = {
            name: "_name",
            price: "_unit_price",
            cost: "_cost",
            base_unit: "_base_unit",
            sell_uom: "_sell_uom",
            pack_qty: "_pack_qty",
            barcode: "_barcode",
            department_id: "_suggested_department",
            quantity: "_delivered_qty",
          };
          onChange(fieldMap[field] || field, value);
        }}
        departments={departments}
        hiddenFields={COMPACT_HIDDEN}
      />

      {item.original_sku && (
        <p className="text-xs text-muted-foreground font-mono">
          Vendor SKU: {item.original_sku}
        </p>
      )}
    </div>
  );
}
