import { useState } from "react";
import { Search, PackageSearch } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

/**
 * Bottom sheet shown when a barcode scan returns "not found".
 *
 * Lets the user search for a product by name/SKU from the already-loaded
 * product list (no extra network call) and manually add it to the cart.
 *
 * Props:
 *   open            boolean
 *   onOpenChange    (open: boolean) => void
 *   barcode         string  — the unrecognised code (shown for context)
 *   products        array   — all products already loaded by the parent page
 *   onAddProduct    (product) => void  — called when user picks a product
 */
export function UnknownBarcodeSheet({ open, onOpenChange, barcode, products = [], onAddProduct }) {
  const [search, setSearch] = useState("");

  const results = search.trim().length > 1
    ? products.filter((p) => {
        const q = search.toLowerCase();
        return (
          p.name?.toLowerCase().includes(q) ||
          p.sku?.toLowerCase().includes(q)
        );
      }).slice(0, 8)
    : [];

  function handleAdd(product) {
    onAddProduct?.(product);
    setSearch("");
    onOpenChange(false);
  }

  function handleClose() {
    setSearch("");
    onOpenChange(false);
  }

  return (
    <Sheet open={open} onOpenChange={handleClose}>
      <SheetContent side="bottom" className="max-h-[75vh] flex flex-col rounded-t-2xl">
        <SheetHeader className="pb-2">
          <SheetTitle className="flex items-center gap-2">
            <PackageSearch className="w-5 h-5 text-warning" />
            Barcode not recognised
          </SheetTitle>
          {barcode && (
            <SheetDescription className="font-mono text-xs">
              Scanned: <span className="text-foreground">{barcode}</span>
            </SheetDescription>
          )}
        </SheetHeader>

        <p className="text-sm text-muted-foreground mb-3">
          Search by product name or SKU to add it manually.
        </p>

        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <Input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search product name or SKU…"
            className="pl-9"
          />
        </div>

        <div className="flex-1 overflow-auto">
          {search.trim().length > 1 && results.length === 0 && (
            <p className="text-center text-sm text-muted-foreground py-8">No products match.</p>
          )}
          {results.map((p) => (
            <button
              key={p.id}
              onClick={() => handleAdd(p)}
              className="w-full flex items-center justify-between px-3 py-3 rounded-lg hover:bg-muted border-b border-border/50 last:border-b-0 text-left"
            >
              <div className="min-w-0">
                <p className="font-mono text-[10px] text-muted-foreground">{p.sku}</p>
                <p className="text-sm font-medium text-foreground truncate">{p.name}</p>
              </div>
              <span className="text-xs text-muted-foreground shrink-0 ml-4">
                {Math.floor(p.sell_quantity ?? p.quantity)} avail
              </span>
            </button>
          ))}
        </div>

        <Button variant="outline" className="mt-3 w-full" onClick={handleClose}>
          Cancel
        </Button>
      </SheetContent>
    </Sheet>
  );
}
