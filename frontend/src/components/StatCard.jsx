import { cn } from "@/lib/utils";

/**
 * Stat card for dashboard KPIs.
 */
export function StatCard({
  label,
  value,
  subtext,
  icon: Icon,
  iconColor = "text-slate-600",
  iconBg = "bg-slate-100",
  className,
}) {
  return (
    <div
      className={cn(
        "card-elevated p-6",
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        {Icon && (
          <div
            className={cn(
              "w-11 h-11 rounded-xl flex items-center justify-center",
              iconBg
            )}
          >
            <Icon className={cn("w-5 h-5", iconColor)} />
          </div>
        )}
      </div>
      <p className="text-sm text-slate-500 font-medium">{label}</p>
      <p className="text-2xl font-semibold text-slate-900 mt-1 tracking-tight">
        {value}
      </p>
      {subtext && (
        <p className="text-xs text-slate-400 mt-2">{subtext}</p>
      )}
    </div>
  );
}
