import { cn } from "@/lib/utils";

export function Money({ value, className }) {
  const formatted = (value ?? 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return <span className={cn("tabular-nums", className)}>{formatted}</span>;
}
