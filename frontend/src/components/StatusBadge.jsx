import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";

const VARIANTS = {
  paid:         "badge-success",
  unpaid:       "badge-warning",
  uninvoiced:   "bg-warning/15 text-warning border border-warning/30",
  overdue:      "badge-error",
  invoiced:     "bg-info/15 text-info border border-info/30",
  draft:        "bg-muted text-muted-foreground border border-border",
  approved:     "bg-warning/15 text-warning border border-warning/30",
  sent:         "bg-info/15 text-info border border-info/30",
  authorised:   "bg-success/15 text-success border border-success/30",
  voided:       "bg-destructive/15 text-destructive border border-destructive/30",
  deleted:      "bg-destructive/15 text-destructive border border-destructive/30",
  pending:      "badge-warning",
  processed:    "badge-success",
  active:       "badge-success",
  inactive:     "bg-muted text-muted-foreground border border-border",
  ordered:      "bg-muted text-muted-foreground border border-border",
  partial:      "bg-info/15 text-info border border-info/30",
  received:     "bg-success/15 text-success border border-success/30",
};

export function StatusBadge({ status, className }) {
  const variant = VARIANTS[status] || "bg-muted text-muted-foreground border border-border";
  return (
    <span className={cn("inline-block px-2.5 py-0.5 rounded-md text-xs font-semibold capitalize", variant, className)}>
      {status}
    </span>
  );
}

/** Inventory stock status badge derived from a product object. */
export function StockBadge({ product, className }) {
  if (product.quantity === 0) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-destructive/15 text-destructive", className)}>
        <XCircle className="w-3.5 h-3.5" />
        Out of Stock
      </span>
    );
  }
  if (product.quantity <= product.min_stock) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-warning/15 text-warning", className)}>
        <AlertTriangle className="w-3.5 h-3.5" />
        Low Stock
      </span>
    );
  }
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/15 text-success", className)}>
      <CheckCircle className="w-3.5 h-3.5" />
      In Stock
    </span>
  );
}
