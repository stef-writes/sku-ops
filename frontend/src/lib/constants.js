export const ROLES = {
  ADMIN: "admin",
  WAREHOUSE_MANAGER: "warehouse_manager",
  CONTRACTOR: "contractor",
};

export const ADMIN_ROLES = [ROLES.ADMIN, ROLES.WAREHOUSE_MANAGER];

export const JOB_STATUSES = {
  ACTIVE: "active",
  COMPLETED: "completed",
  CANCELLED: "cancelled",
};

export const PAYMENT_METHODS = [
  { value: "bank_transfer", label: "Bank Transfer" },
  { value: "check", label: "Check" },
  { value: "cash", label: "Cash" },
  { value: "credit_card", label: "Credit Card" },
  { value: "other", label: "Other" },
];

export const INVOICE_STATUSES = {
  DRAFT: "draft",
  APPROVED: "approved",
  SENT: "sent",
  PAID: "paid",
};

export const DOCUMENT_STATUSES = {
  PARSED: "parsed",
  IMPORTED: "imported",
  REJECTED: "rejected",
};

export const UOM_OPTIONS = [
  "each", "case", "box", "pack", "bag", "roll", "gallon", "quart", "pint",
  "liter", "pound", "ounce", "foot", "meter", "yard", "sqft", "kit",
];

export const ADJUST_REASONS = [
  { value: "correction", label: "Correction" },
  { value: "count", label: "Count" },
  { value: "damage", label: "Damage" },
  { value: "theft", label: "Theft" },
  { value: "return", label: "Return" },
];

export const TX_TYPE_LABELS = {
  withdrawal: "Withdrawal",
  import: "Import",
  adjustment: "Adjustment",
  receiving: "Receiving",
  return: "Return",
  transfer: "Transfer",
};

export const DATE_PRESETS = [
  {
    label: "Today",
    getValue: () => { const d = new Date(); return { from: d, to: d }; },
  },
  {
    label: "Last 7 days",
    getValue: () => {
      const end = new Date();
      const start = new Date(end);
      start.setDate(start.getDate() - 6);
      return { from: start, to: end };
    },
  },
  {
    label: "This month",
    getValue: () => {
      const end = new Date();
      const start = new Date(end.getFullYear(), end.getMonth(), 1);
      return { from: start, to: end };
    },
  },
  { label: "All time", getValue: () => ({ from: null, to: null }) },
];

export const PAGE_SIZES = {
  DEFAULT: 10,
  INVENTORY: 50,
};

export const DEPT_COLORS = {
  LUM: "bg-amber-100 text-amber-700",
  PLU: "bg-blue-100 text-blue-700",
  ELE: "bg-yellow-100 text-yellow-700",
  PNT: "bg-purple-100 text-purple-700",
  TOL: "bg-red-100 text-red-700",
  HDW: "bg-slate-100 text-slate-700",
  GDN: "bg-green-100 text-green-700",
  APP: "bg-cyan-100 text-cyan-700",
};

export function getDeptColor(code) {
  return DEPT_COLORS[code] || "bg-orange-100 text-orange-700";
}
