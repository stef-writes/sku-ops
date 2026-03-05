import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";

const VARIANTS = {
  paid:         "badge-success",
  unpaid:       "badge-warning",
  uninvoiced:   "bg-amber-50 text-amber-700 border border-amber-200",
  overdue:      "badge-error",
  invoiced:     "bg-blue-50 text-blue-700 border border-blue-200",
  draft:        "bg-slate-100 text-slate-600 border border-slate-200",
  approved:     "bg-amber-50 text-amber-700 border border-amber-200",
  sent:         "bg-blue-50 text-blue-700 border border-blue-200",
  authorised:   "bg-emerald-50 text-emerald-700 border border-emerald-200",
  voided:       "bg-red-50 text-red-700 border border-red-200",
  deleted:      "bg-red-50 text-red-700 border border-red-200",
  pending:      "badge-warning",
  processed:    "badge-success",
  active:       "badge-success",
  inactive:     "bg-slate-100 text-slate-500 border border-slate-200",
  ordered:      "bg-slate-100 text-slate-600 border border-slate-200",
  partial:      "bg-blue-50 text-blue-700 border border-blue-200",
  received:     "bg-emerald-50 text-emerald-700 border border-emerald-200",
};

export function StatusBadge({ status, className }) {
  const variant = VARIANTS[status] || "bg-slate-100 text-slate-600 border border-slate-200";
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
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700", className)}>
        <XCircle className="w-3.5 h-3.5" />
        Out of Stock
      </span>
    );
  }
  if (product.quantity <= product.min_stock) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700", className)}>
        <AlertTriangle className="w-3.5 h-3.5" />
        Low Stock
      </span>
    );
  }
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700", className)}>
      <CheckCircle className="w-3.5 h-3.5" />
      In Stock
    </span>
  );
}
